"""
CinematographerAgent — builds Gemini Omni Flash shot prompts.

Design principles:
1. NO extra LLM call per scene. The prompt is built deterministically from
   the character visuals, drama beat, and dialogue. Calling Gemini here
   burned quota mid-render and caused 429s that failed clips.

2. CHARACTER BIBLE at the top of every prompt, always.
    Omni reads the beginning of the prompt first. If Peter Parker's full
    physical description appears first in every clip, it anchors his
   face and costume consistently. Buried in a paragraph = ignored.

3. VISUAL STATE carried forward between clips.
   Time of day, lighting condition, and costume state from the previous
   scene are repeated verbatim. This is why real films feel continuous.

4. SENSORY language only — what the camera SEES, what the SOUND is,
   what the LIGHT does, who MOVES. No meta-words like "pacing: climax".
"""

import math
import re
from typing import List, Dict, Optional

from core.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Terms that trigger Omni's content filters (copyrighted characters AND
# real prominent individuals). Replaced before any prompt is sent.
# ─────────────────────────────────────────────────────────────────────────────
_IP_REPLACEMENTS = {
    # Marvel / DC heroes & villains
    "spider-man": "the masked vigilante",
    "spider man": "the masked vigilante",
    "spiderman": "the masked vigilante",
    "peter parker": "the vigilante",
    "batman": "the dark knight detective",
    "bruce wayne": "the detective",
    "superman": "the caped hero",
    "clark kent": "the hero",
    "iron man": "the armoured hero",
    "tony stark": "the armoured hero",
    "captain america": "the super-soldier",
    "steve rogers": "the super-soldier",
    "thor": "the thunder warrior",
    "hulk": "the green giant",
    "joker": "the clown criminal",
    "thanos": "the cosmic warlord",
    "black widow": "the spy",
    "natasha romanoff": "the spy",
    "hawkeye": "the archer",
    "black panther": "the warrior king",
    "doctor strange": "the sorcerer",
    "scarlet witch": "the witch",
    "wanda maximoff": "the witch",
    "green goblin": "the armoured villain",
    # Star Wars
    "darth vader": "the dark lord",
    "luke skywalker": "the young hero",
    "yoda": "the ancient sage",
    "han solo": "the smuggler",
    "princess leia": "the rebel leader",
    "obi-wan": "the old mentor",
    # Harry Potter
    "harry potter": "the young wizard",
    "hermione": "the witch scholar",
    "voldemort": "the dark wizard",
    "dumbledore": "the elder wizard",
    # Real directors / artists that Omni flags as prominent individuals
    "makoto shinkai": "a celebrated animation studio",
    "christopher nolan": "a cinematic director",
    "stanley kubrick": "a classic director",
    "steven spielberg": "a blockbuster director",
    "quentin tarantino": "an indie director",
    "wes anderson": "a stylised director",
    "david fincher": "a thriller director",
    # Common suit/costume descriptors that map to known IP
    "red-and-blue nano-suit": "sleek metallic armoured suit",
    "red and blue nano-suit": "sleek metallic armoured suit",
    "red-and-blue suit": "sleek metallic armoured suit",
    "web-slinging": "acrobatic movement",
    "web slinging": "acrobatic movement",
    "nano-suit": "advanced armoured suit",
    "bat-suit": "dark tactical armour",
    "batsuit": "dark tactical armour",
    "kryptonite": "a glowing mineral weakness",
    "lightsaber": "an energy blade",
    "the force": "telekinetic power",
}


def _sanitise_prompt(text: str) -> str:
    """Replace known IP-sensitive names and real-person references."""
    result = text
    for ip_term, replacement in _IP_REPLACEMENTS.items():
        result = re.sub(re.escape(ip_term), replacement, result, flags=re.IGNORECASE)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Visual style → sensory language for the Omni prompt.
# No real director or artist names — Omni flags those as prominent individuals.
# ─────────────────────────────────────────────────────────────────────────────
STYLE_LANGUAGE = {
    "cinematic": (
        "35mm anamorphic, shallow focus, motivated practical lighting, "
        "film grain, warm golden-hour tones, slow dolly movements"
    ),
    "anime": (
        "hand-drawn Japanese animation, vibrant cel-shading color palette, "
        "saturated sky, kinetic speed lines on action, "
        "detailed backgrounds, dramatic close-up expressions"
    ),
    "documentary": (
        "handheld 16mm verité, natural ambient light, intimate close-ups, "
        "slightly underexposed, diegetic sound, no score — only room tone"
    ),
    "noir": (
        "black and white, venetian blind shadow stripes, rain-slicked "
        "cobblestones, cigarette smoke, 1940s wardrobe, low-angle shots, "
        "single harsh key light from one side"
    ),
    # Advertising has its own grammar. Commercials are lit brighter and cleaner
    # than drama, the product stays sharp and legible, and the camera is stable
    # because a viewer must be able to read the product in a few seconds.
    "commercial": (
        "bright high-key commercial lighting, clean soft shadows, glossy product "
        "surfaces in crisp focus, shallow depth of field behind the product, "
        "smooth stabilised camera moves, saturated but natural colour, "
        "uncluttered backgrounds, tabletop macro detail on the product"
    ),
}


class CinematographerAgent:
    """
    Builds Omni shot prompts. No LLM calls — just structured, frozen, vivid text.
    """

    def __init__(self):
        self._video_duration_seconds = 10
        self.film_duration_minutes = 5
        self.aspect_ratio = "16:9"
        self.visual_style = "cinematic"
        self._scenes_generated = 0

        # Frozen character visuals — set once at render start, never changed.
        # Shape: {name: "exact physical description"}
        self.character_visuals: Dict[str, str] = {}

        # Visual state carried forward between clips so Omni doesn't reset.
        # Shape: {name: "last-seen state note e.g. 'shirt torn, bleeding lip'"}
        self._character_state: Dict[str, str] = {}

        # Last clip's environment (time of day, weather, lighting)
        self._last_environment: str = ""

        # One-line summary of each prior scene — injected as context
        self.scene_history: List[str] = []

    def set_character_visuals(self, character_visuals: Dict[str, str]) -> None:
        """Start a fresh production with a frozen character bible.

        The previous implementation only reset per-character state.  Scene
        counters, history, and lighting leaked from one film into the next when
        Cloud Run reused the process, which produced genuinely unrelated prompts
        claiming to be continuous.  A new production must reset all of them.
        """
        self.character_visuals = {k: v for k, v in character_visuals.items() if v}
        self._character_state = {}
        self._last_environment = ""
        self.scene_history = []
        self._scenes_generated = 0

    @property
    def video_duration(self) -> str:
        return f"{self._video_duration_seconds}s"

    @video_duration.setter
    def video_duration(self, value: str) -> None:
        try:
            secs = int(str(value).replace("s", ""))
        except ValueError:
            secs = 10
        # The Omni harness uses explicit 10-second scene units.  Do not alter a
        # requested duration silently; the Studio validates it before rendering.
        self._video_duration_seconds = secs if secs > 0 else 10

    @property
    def total_clips_needed(self) -> int:
        return math.ceil((self.film_duration_minutes * 60) / self._video_duration_seconds)

    @property
    def film_progress_pct(self) -> float:
        if self.total_clips_needed == 0:
            return 1.0
        return min(self._scenes_generated / self.total_clips_needed, 1.0)

    async def generate_omni_prompt(
        self,
        drama_beat: str,
        characters_involved: List[str],
        location: Optional[str] = None,
        dialogues: Optional[List[Dict]] = None,
        continuity: Optional[Dict] = None,
        critique_feedback: str = "",
    ) -> str:
        """
        Build the Omni shot prompt for one scene.

        Prompt structure (ORDER MATTERS — Omni reads top-down):
          1. CHARACTER BIBLE — frozen physical descriptions of every character
              in this scene. Omni anchors its visual generation here first.
          2. ENVIRONMENT — time of day, weather, lighting inherited from
             the previous scene (or established fresh for scene 1).
          3. SHOT — camera position, movement, framing.
          4. ACTION — who does what, in what order, with what expression.
          5. DIALOGUE — spoken lines embedded naturally.
          6. SOUND — ambient sound, music cue, silence.
          7. STYLE — the film's visual language.
        """
        # This method is deliberately side-effect free. A rejected candidate
        # must not advance the scene counter or leak its environment/history into
        # the accepted film chain. ``commit_scene`` below is called only after
        # the Director accepts a render.
        n = self._scenes_generated + 1
        total = self.total_clips_needed
        style = STYLE_LANGUAGE.get(self.visual_style, STYLE_LANGUAGE["cinematic"])

        # ── 1. CHARACTER BIBLE ────────────────────────────────────────────────
        # Every character who appears in this scene gets their FULL frozen
        # description at the top. Omni reads this first and anchors the face,
        # costume, and build for the entire clip.
        bible_lines: List[str] = []
        for name in characters_involved:
            base_desc = self.character_visuals.get(name, "")
            state_note = self._character_state.get(name, "")
            if base_desc:
                entry = f"{name}: {base_desc}"
                if state_note:
                    entry += f" — {state_note}"
                bible_lines.append(entry)

        bible_section = ""
        if bible_lines:
            bible_section = "CHARACTER APPEARANCES (keep exactly consistent with previous clips):\n"
            bible_section += "\n".join(f"• {line}" for line in bible_lines)

        # ── 2. ENVIRONMENT ────────────────────────────────────────────────────
        # Inherit from last scene or establish fresh for scene 1.
        continuity = continuity or {}
        planned_environment = str(continuity.get("environment_state") or "").strip()
        if planned_environment:
            env_note = planned_environment
        elif self._last_environment:
            env_note = f"Continuous from previous scene: {self._last_environment}."
        else:
            # Scene 1 — establish environment from location name.
            env_note = _infer_environment(location or "interior", self.visual_style)

        # ── 3. PRIOR SCENES (last 3) ──────────────────────────────────────────
        prior_note = ""
        if self.scene_history:
            prior_note = "Previously: " + " → ".join(self.scene_history[-3:]) + "."

        # ── 4. DIALOGUE ───────────────────────────────────────────────────────
        dialogue_lines: List[str] = []
        if dialogues:
            for d in dialogues:
                name = d.get("character_name", d.get("character", ""))
                line = d.get("line", d.get("text", ""))
                if name and line:
                    dialogue_lines.append(f'{name} says: "{line.strip()}"')

        # ── BUILD THE FINAL PROMPT ────────────────────────────────────────────
        # Written as a present-tense shot description, not a form or template.
        parts: List[str] = []

        # Character bible FIRST
        if bible_section:
            parts.append(bible_section)

        # Environment
        parts.append(f"Setting: {location or 'interior'}. {env_note}")

        # Prior context supports the deterministic prompt ledger in addition to
        # Omni's stateful previous_interaction_id chain.
        if prior_note:
            parts.append(prior_note)

        transition = str(continuity.get("transition_from_previous") or "").strip()
        if transition:
            parts.append(f"Continuity transition: {transition}")

        # Framing & Aspect Ratio
        if self.aspect_ratio == "9:16":
            parts.append(
                "Framing & Aspect Ratio: 9:16 vertical portrait format (full-height mobile composition, vertical framing, no letterboxing or horizontal borders)."
            )
        else:
            parts.append(
                "Framing & Aspect Ratio: 16:9 widescreen landscape format (horizontal cinematic composition)."
            )

        # The shot itself
        parts.append(f"Scene {n} of {total}: {drama_beat}")

        # Dialogue embedded as audible voice lines with audio direction
        if dialogue_lines:
            dialogue_str = "  ".join(dialogue_lines)
            parts.append(
                f"AUDIO & SPOKEN DIALOGUE / VOICEOVER: The video must feature clear, audible spoken voice acting with synchronized audio. {dialogue_str}. High clarity voice track with natural ambient environment sound."
            )

        # Style
        parts.append(f"Visual style: {style}.")

        # A failed review supplies precise repair instructions.  Keep it bounded
        # and declarative so it cannot overwrite the character bible above.
        if critique_feedback:
            parts.append(
                "Correction from continuity review: "
                + critique_feedback.strip().replace("\n", " ")[:600]
            )

        prompt = _sanitise_prompt("\n\n".join(parts))

        logger.info(
            f"[Cinematographer] Omni scene {n}/{total} "
            f"({min(n / max(total, 1), 1.0):.0%}) prompt={len(prompt)} chars"
        )
        return prompt

    async def generate_veo_prompt(
        self,
        drama_beat: str,
        characters_involved: List[str],
        location: Optional[str] = None,
        dialogues: Optional[List[Dict]] = None,
    ) -> str:
        """Compatibility alias for the dormant Veo experiment.

        It emits the same deterministic visual ledger but does not select the
        renderer. The active Studio Engine invokes ``generate_omni_prompt``.
        """
        return await self.generate_omni_prompt(
            drama_beat=drama_beat,
            characters_involved=characters_involved,
            location=location,
            dialogues=dialogues,
        )

    def update_character_state(self, name: str, state_note: str) -> None:
        """
        Call after a clip renders to record visible changes to a character
        (injury, costume tear, emotional state shift) so the next scene
        can carry that state forward in the CHARACTER BIBLE.
        """
        self._character_state[name] = state_note

    def update_environment_state(self, environment_note: str) -> None:
        """Persist a verified scene-level environment change for the next shot."""
        self._last_environment = environment_note

    def commit_scene(
        self,
        *,
        location: Optional[str],
        drama_beat: str,
        environment_state: str = "",
    ) -> None:
        """Commit visual context only after a shot passed Director review."""
        self._scenes_generated += 1
        loc_str = f"{location} — " if location else ""
        self.scene_history.append(f"{loc_str}{drama_beat[:100].rstrip()}")
        if environment_state.strip():
            self._last_environment = environment_state.strip()
        elif not self._last_environment:
            self._last_environment = _infer_environment(location or "interior", self.visual_style)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _infer_environment(location: str, style: str) -> str:
    """
    Derive a starting environment description from the location name.
    This anchors scene 1 so that subsequent scenes can inherit from it.
    """
    loc = location.lower()
    if any(w in loc for w in ("night", "dark", "bar", "club", "basement", "underground")):
        base = "night, artificial lighting, deep shadows"
    elif any(w in loc for w in ("dawn", "morning", "sunrise", "early")):
        base = "early morning, soft blue light, mist"
    elif any(w in loc for w in ("noon", "midday", "sun", "desert", "rooftop")):
        base = "harsh midday sun, high contrast, no shadows below"
    elif any(w in loc for w in ("evening", "sunset", "dusk", "golden")):
        base = "golden hour, warm side-light, long shadows"
    elif any(w in loc for w in ("rain", "storm", "thunder", "wet")):
        base = "overcast, rain-soaked surfaces, cold diffuse light"
    elif any(w in loc for w in ("space", "station", "ship", "orbit")):
        base = "zero-gravity, hard vacuum light from one side, deep black void"
    elif any(w in loc for w in ("lab", "hospital", "corridor", "office")):
        base = "fluorescent overhead, clinical white walls, cold blue cast"
    else:
        base = "overcast daylight, soft diffuse shadows, neutral tones"

    if style == "noir":
        base = "night, single harsh key light, venetian blind shadows, no fill"
    elif style == "anime":
        base = "dramatic sky with cumulonimbus clouds, vibrant saturated light"
    elif style == "commercial":
        # Advertising overrides the location-derived mood on purpose: a product
        # has to stay clearly legible, so a commercial does not inherit the
        # "deep shadows" or "underexposed" treatments the dramatic styles use.
        base = "bright even high-key light, clean white bounce fill, no deep shadows"

    return base
