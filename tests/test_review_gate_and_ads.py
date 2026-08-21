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
