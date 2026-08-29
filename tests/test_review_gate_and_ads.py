"""Tests for the continuity review gate, honest tension, and the Ads Specialist.

These cover the behaviours that replaced silent auto-approval:
  - a clip is never labelled director_approved without a real critic verdict
  - an unscored beat stays None instead of becoming a confident 0.0
  - ad copy claims are rewritten deterministically
  - an ad always ends on its call to action
"""

import asyncio

import pytest

from agents.ads_agent import AdsSpecialistAgent, apply_ad_compliance, is_ad_style
from core.studio_engine import StudioEngine
from models.schema import SceneRecord


def run(coro):
    return asyncio.run(coro)


class FakeCinematographer:
    def __init__(self):
        self.character_visuals = {"Ana": "woman, 30s, red coat"}


class FakeDirector:
    """Stands in for the visual critic. ``verdict`` may be a dict or an Exception."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0
        self.last_expected = None

    async def critique_scene(self, scene, video_uri, expected=None):
        self.calls += 1
        self.last_expected = expected
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return self.verdict


def make_engine(review_mode, verdict):
    """Build a StudioEngine without __init__, which needs live Vertex credentials."""
    engine = object.__new__(StudioEngine)
    engine.review_mode = review_mode
    engine.director = FakeDirector(verdict)
    engine.cinematographer = FakeCinematographer()
    return engine


def make_scene():
    return SceneRecord(
        scene_id="s01",
        video_uri="https://example.test/v.mp4",
        status="rendering",
        anchor_names=["Ana"],
    )


SCENE_DATA = {
    "location": "Rooftop",
    "drama_beat": "Ana steps to the ledge.",
    "characters_involved": ["Ana"],
    "dialogues": [],
    "continuity": {},
}

APPROVED = {"approved": True, "continuity_score": 0.91, "critique": "Identity holds."}
REJECTED = {
    "approved": False,
    "continuity_score": 0.32,
    "critique": "Face changed.",
    "revised_prompt": "Keep Ana identical.",
}


# ---------------------------------------------------------------------------
# Review gate
# ---------------------------------------------------------------------------

def test_approved_clip_is_labelled_director_approved():
    engine = make_engine("enforce", APPROVED)
    accepted, verdict = run(
        engine._review_rendered_scene(make_scene(), "gs://b/v.mp4", dict(SCENE_DATA))
    )
    assert accepted is True
    assert verdict["review_mode"] == "director_approved"
    assert verdict["continuity_score"] == pytest.approx(0.91)


def test_enforce_mode_rejects_a_failed_verdict():
    engine = make_engine("enforce", REJECTED)
    accepted, verdict = run(
        engine._review_rendered_scene(make_scene(), "gs://b/v.mp4", dict(SCENE_DATA))
    )
    assert accepted is False
    assert verdict["review_mode"] == "unverified"
    assert verdict["revised_prompt"] == "Keep Ana identical."


def test_advisory_mode_keeps_the_clip_but_never_calls_it_approved():
    engine = make_engine("advisory", REJECTED)
    accepted, verdict = run(
        engine._review_rendered_scene(make_scene(), "gs://b/v.mp4", dict(SCENE_DATA))
    )
    assert accepted is True
    assert verdict["review_mode"] == "unverified"
    # The real score survives; it is not rounded up to resemble an approval.
    assert verdict["continuity_score"] == pytest.approx(0.32)


def test_review_off_skips_the_critic_entirely():
    engine = make_engine("off", APPROVED)
    accepted, verdict = run(
        engine._review_rendered_scene(make_scene(), "gs://b/v.mp4", dict(SCENE_DATA))
    )
    assert accepted is True
    assert verdict["review_mode"] == "review_disabled"
    assert verdict["continuity_score"] is None
    assert engine.director.calls == 0


def test_a_crashing_critic_is_not_an_approval():
    engine = make_engine("enforce", RuntimeError("429 quota exceeded"))
    accepted, verdict = run(
        engine._review_rendered_scene(make_scene(), "gs://b/v.mp4", dict(SCENE_DATA))
    )
    assert accepted is False
    assert verdict["review_mode"] == "unverified"
    assert "could not run" in verdict["critique"]


def test_critic_receives_the_visual_bible_as_the_shot_contract():
    engine = make_engine("enforce", APPROVED)
    run(engine._review_rendered_scene(make_scene(), "gs://b/v.mp4", dict(SCENE_DATA)))
    expected = engine.director.last_expected
    assert expected["character_visual_bible"]["Ana"] == "woman, 30s, red coat"
    assert expected["reference_images_supplied"] == ["Ana"]


# ---------------------------------------------------------------------------
# Honest tension and scene validation
# ---------------------------------------------------------------------------

def test_absent_tension_stays_none_rather_than_zero():
    scene = StudioEngine._normalise_scene(
        {"location": "Bar", "drama_beat": "Ana waits.", "characters_involved": ["Ana"]},
        {"Ana"},
    )
    assert scene["tension"] is None


def test_supplied_tension_is_clamped():
    def build(value):
        return StudioEngine._normalise_scene(
            {
                "location": "Bar",
                "drama_beat": "Ana waits.",
                "characters_involved": ["Ana"],
                "tension": value,
            },
            {"Ana"},
        )

    assert build(4.2)["tension"] == 1.0
    assert build(-1)["tension"] == 0.0
    assert build("hot")["tension"] is None


def test_drama_requires_a_cast_but_an_ad_may_be_product_only():
    raw = {
        "location": "White studio",
        "drama_beat": "The bottle rotates.",
        "characters_involved": [],
    }
    assert StudioEngine._normalise_scene(raw, {"Ana"}) is None
    ad = StudioEngine._normalise_scene(raw, {"Ana"}, allow_empty_cast=True)
    assert ad is not None
    assert ad["characters_involved"] == []


def test_unknown_characters_are_dropped():
    scene = StudioEngine._normalise_scene(
        {
            "location": "Bar",
            "drama_beat": "Ana waits.",
            "characters_involved": ["Ana", "Ghost"],
        },
        {"Ana"},
    )
    assert scene["characters_involved"] == ["Ana"]


def test_scene_asset_labels_are_deduplicated():
    scene = StudioEngine._normalise_scene(
        {
            "location": "Bar",
            "drama_beat": "Ana waits.",
            "characters_involved": ["Ana"],
            "scene_asset_labels": ["plate", "plate", "prop"],
        },
        {"Ana"},
    )
    assert scene["scene_asset_labels"] == ["plate", "prop"]


# ---------------------------------------------------------------------------
# Ads specialist
# ---------------------------------------------------------------------------

def test_risky_claims_are_rewritten_and_reported():
    clean, flags = apply_ad_compliance(
        "Our clinically proven cream is the world's best and 100% guaranteed."
    )
    assert "clinically proven" not in clean.lower()
    assert "unsubstantiated_clinical_claim" in flags
    assert "unverifiable_superlative" in flags


def test_benign_copy_is_left_alone():
    text = "A woman pours coffee at sunrise."
    clean, flags = apply_ad_compliance(text)
    assert clean == text
    assert flags == []


def test_ad_styles_are_recognised():
    assert is_ad_style("commercial")
    assert is_ad_style("Ads")
    assert not is_ad_style("noir")


def test_missing_call_to_action_is_appended_and_reported():
    report = {"cta_appended": False}
    shots = [{"drama_beat": "The pack sits on a table.", "dialogues": []}]
    AdsSpecialistAgent._enforce_cta(shots, "Order yours today", report)
    assert report["cta_appended"] is True
    assert "Order yours today" in shots[-1]["drama_beat"]


def test_existing_call_to_action_is_not_duplicated():
    report = {"cta_appended": False}
    shots = [{"drama_beat": "Type reads: order yours today.", "dialogues": []}]
    AdsSpecialistAgent._enforce_cta(shots, "Order yours today", report)
    assert report["cta_appended"] is False


def test_compliance_runs_over_dialogue_not_just_action():
    agent = object.__new__(AdsSpecialistAgent)
    report = {"compliance_rewrites": 0, "compliance_flags": []}
    shots = agent._scrub_shots(
        [
            {
                "drama_beat": "She smiles.",
                "dialogues": [
                    {"character_name": "Ana", "line": "It is 100% guaranteed."}
                ],
            }
        ],
        report,
    )
    assert "guaranteed" not in shots[0]["dialogues"][0]["line"].lower()
    assert report["compliance_rewrites"] == 1


# ---------------------------------------------------------------------------
# Client-supplied brand name
# ---------------------------------------------------------------------------

def test_brand_hint_reaches_the_campaign_brief_prompt():
    """A supplied brand must be stated to the strategist, not inferred."""
    agent = object.__new__(AdsSpecialistAgent)
    captured = {}

    async def fake_generate_json(prompt, expect_list=False):
        captured["prompt"] = prompt
        return {"brand": "Aether Running Shoes", "product": "trail shoes"}

    agent._generate_json = fake_generate_json
    brief = run(
        agent.build_campaign_brief(
            premise="A runner crosses a ridge at dawn.",
            characters=[{"name": "Ana"}],
            total_clips=2,
            clip_duration=10,
            brand_hint="Aether Running Shoes",
        )
    )
    assert "Aether Running Shoes" in captured["prompt"]
    assert brief["brand"] == "Aether Running Shoes"
    # 2 clips x 10s: the brief must describe the real runtime.
    assert brief["runtime_seconds"] == 20


def test_blank_brand_hint_does_not_claim_a_client_supplied_name():
    agent = object.__new__(AdsSpecialistAgent)
    captured = {}

    async def fake_generate_json(prompt, expect_list=False):
        captured["prompt"] = prompt
        return {}

    agent._generate_json = fake_generate_json
    brief = run(
        agent.build_campaign_brief(
            premise="A cup of coffee at sunrise.",
            characters=[],
            total_clips=1,
            clip_duration=10,
        )
    )
    assert "BRAND NAME SUPPLIED BY THE CLIENT" not in captured["prompt"]
    # Falls back rather than inventing a brand the client never gave.
    assert brief["brand"] == "the product"


def test_brand_is_threaded_through_both_studio_entry_points():
    """Guards a real break: passing brand= to a signature that lacks it raises
    TypeError at request time, on the legacy /start_simulation path."""
    import inspect

    assert "brand" in inspect.signature(StudioEngine.simulate_script).parameters
    assert "brand" in inspect.signature(StudioEngine.generate_movie).parameters


def test_ad_normalisation_permits_voiceover_and_narrator_dialogue():
    """Ads often have off-screen Voiceover or Narrator, which must not be stripped."""
    scene = {
        "location": "Modern Kitchen",
        "drama_beat": "A sleek blender whips a smoothie in seconds.",
        "characters_involved": [],
        "dialogues": [
            {"character_name": "Voiceover", "line": "Start your day with pure energy."},
        ],
    }
    normalised = StudioEngine._normalise_scene(scene, set(), allow_empty_cast=True)
    assert normalised is not None
    assert len(normalised["dialogues"]) == 1
    assert normalised["dialogues"][0]["character_name"] == "Voiceover"
    assert normalised["dialogues"][0]["line"] == "Start your day with pure energy."


def test_cinematographer_aspect_ratio_and_audio_prompts():
    """Cinematographer must generate explicit 9:16 vertical directives and audio cues."""
    from agents.cinematographer_agent import CinematographerAgent

    agent = CinematographerAgent()
    agent.aspect_ratio = "9:16"
    agent.set_character_visuals({"Maya": "runner in teal jacket"})

    prompt = run(
        agent.generate_omni_prompt(
            drama_beat="Maya laces her shoes and smiles.",
            characters_involved=["Maya"],
            location="Trailhead",
            dialogues=[{"character_name": "Maya", "line": "Ready to go."}],
        )
    )
    assert "9:16 vertical portrait format" in prompt
    assert "AUDIO & SPOKEN DIALOGUE / VOICEOVER" in prompt
    assert 'Maya says: "Ready to go."' in prompt

    # Test 16:9 widescreen
    agent.aspect_ratio = "16:9"
    prompt_16_9 = run(
        agent.generate_omni_prompt(
            drama_beat="Maya laces her shoes.",
            characters_involved=["Maya"],
            location="Trailhead",
        )
    )
    assert "16:9 widescreen landscape format" in prompt_16_9


def test_video_editor_aspect_ratio_parameter():
    """VideoEditor.compile_movie must accept and process aspect_ratio."""
    import inspect
    from core.video_editor import VideoEditor

    sig = inspect.signature(VideoEditor.compile_movie)
    assert "aspect_ratio" in sig.parameters

