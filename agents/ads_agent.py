"""AdsSpecialistAgent - the advertising and commercial production specialist.

Cinematic, anime, documentary, and noir productions are dramatic: their shot
lists escalate conflict. An advertisement does not. It has a fixed persuasive
arc, a hard runtime, a product whose appearance must stay accurate, and claims
that carry legal weight.

This agent owns that difference:

1. It writes a campaign brief (brand, product, audience, ONE value
   proposition, tone, call to action) BEFORE any shot exists, so the shot list
   derives from a stated strategy instead of improvised drama.
2. It generates the shot list against the advertising arc
   hook -> problem -> product reveal -> proof -> call to action, rather than
   setup -> pressure -> reversal -> climax -> consequence.
3. It runs a deterministic compliance pass. Unverifiable superlatives and
   health or financial claims are rewritten and reported, because an ad that
   invents "clinically proven" is a real liability, not a style choice.
4. It verifies the call to action survives into the final shot, and reports
   plainly when one had to be appended instead of pretending the writer
   produced it.

The returned shot list uses the same shape as the dramatic screenwriter, so the
render path, continuity ledger, and Director gate are shared unchanged.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Tuple

from google.api_core.exceptions import ResourceExhausted
from vertexai.generative_models import GenerativeModel

from agents.cinematographer_agent import _sanitise_prompt
from core.logger import get_logger

logger = get_logger(__name__)

# Visual styles that route through this agent instead of the drama screenwriter.
AD_STYLES = {"commercial", "ads", "advertisement", "advert"}

# The persuasive arc. Positions are assigned proportionally across the shot
# count so a 6-shot and a 24-shot ad both keep a real structure.
AD_ARC: Tuple[str, ...] = (
    "HOOK: arrest attention in the first seconds with a concrete visual, not a logo.",
    "PROBLEM: show the specific friction the audience already feels.",
    "PRODUCT REVEAL: introduce the product clearly and legibly in frame.",
    "PROOF: demonstrate the benefit actually happening, visibly.",
    "CALL TO ACTION: state the single action the viewer should take.",
)

# Claims a generative writer must never invent. Each entry maps a detection
# pattern to a defensible rewrite. This runs deterministically after generation
# because a model instructed not to over-claim still does.
_CLAIM_RULES: Tuple[Tuple[str, str, str], ...] = (
    (r"\bclinically proven\b", "designed to help", "unsubstantiated_clinical_claim"),
    (r"\b(?:FDA|WHO)[\s-]?approved\b", "regulator-compliant", "unsubstantiated_regulatory_claim"),
    (r"\bdoctors? (?:recommend|approved?)\b", "made with professional input",
     "unsubstantiated_medical_endorsement"),
    (r"\b(?:cures?|curing)\b", "helps with", "medical_cure_claim"),
    (r"\b(?:treats?|prevents?) (?:cancer|diabetes|covid[\w-]*)\b", "supports wellbeing",
     "serious_disease_claim"),
    (r"\b100% (?:guaranteed|effective|safe)\b", "built for reliability", "absolute_guarantee_claim"),
    (r"\bguaranteed (?:returns?|profits?|income|results?)\b", "designed for results",
     "financial_guarantee_claim"),
    (r"\brisk[\s-]free\b", "low-commitment", "risk_free_claim"),
    (r"\bno\.?\s?1\b|\bnumber one\b|\bworld.?s best\b|\bbest[\s-]ever\b",
     "a leading choice", "unverifiable_superlative"),
    (r"\bcheapest\b|\blowest price (?:ever|anywhere)\b", "competitively priced",
     "unverifiable_price_claim"),
    (r"\blose \d+\s*(?:kg|kgs|kilos|pounds|lbs)\b", "support your goals",
     "quantified_weight_loss_claim"),
    (r"\bmiracle\b", "notable", "miracle_claim"),
)


def apply_ad_compliance(text: str) -> Tuple[str, List[str]]:
    """Rewrite legally risky ad copy. Returns the clean text and rule names hit.

    Deterministic on purpose: it is the last line of defence before a claim
    reaches a rendered video, so it must not depend on another model call
    succeeding.
    """
    if not text:
        return "", []
    cleaned = text
    triggered: List[str] = []
    for pattern, replacement, rule in _CLAIM_RULES:
        cleaned, count = re.subn(pattern, replacement, cleaned, flags=re.IGNORECASE)
        if count:
            triggered.append(rule)
    return cleaned, triggered


def is_ad_style(visual_style: str) -> bool:
    """True when a production should be planned as an advertisement."""
    return str(visual_style or "").strip().lower() in AD_STYLES


def _arc_position(index: int, total: int) -> str:
    """Map a shot index onto the advertising arc."""
    if total <= 1:
        return AD_ARC[-1]
    if index == total - 1:
        return AD_ARC[-1]
    slot = int(index * (len(AD_ARC) - 1) / max(total - 1, 1))
    return AD_ARC[min(slot, len(AD_ARC) - 1)]


class AdsSpecialistAgent:
    """Plans advertisements: brief first, then a compliant, CTA-terminated shot list."""

    def __init__(self, model_name: str = "gemini-3.5-flash"):
        self.model = GenerativeModel(model_name)

    # -------------------------------------------------------------------------
    # Phase 1 - strategy
    # -------------------------------------------------------------------------

    async def build_campaign_brief(
        self,
        *,
        premise: str,
        characters: List[Dict[str, Any]],
        total_clips: int,
        clip_duration: int,
        brand_hint: str = "",
    ) -> Dict[str, Any]:
        """Derive an explicit campaign strategy from the premise.

        The brief is generated before shots because an ad without a stated value
        proposition and call to action produces pretty footage that sells
        nothing. On model failure this returns a conservative premise-derived
        brief rather than blocking the production.
        """
        names = ", ".join(str(c.get("name", "")) for c in characters if c.get("name"))
        runtime = total_clips * clip_duration
        brand_line = f"BRAND NAME SUPPLIED BY THE CLIENT: {brand_hint}" if brand_hint else ""
        prompt = f"""You are a senior advertising strategist. Read the product premise and
return the campaign brief that a {runtime}-second commercial will be built from.

PRODUCT PREMISE:
{premise}

ON-SCREEN TALENT AVAILABLE: {names or "none named"}
{brand_line}

Return ONLY a JSON object:
{{
  "brand": "the brand or product name as it should appear on screen",
  "product": "what is actually being sold, in one concrete phrase",
  "audience": "the specific person this ad speaks to",
  "value_proposition": "ONE benefit, stated plainly. Not a list.",
  "tone": "three adjectives for the delivery",
  "call_to_action": "the single action the viewer should take, 3 to 8 words",
  "product_visual": "how the product must look in every shot so it stays recognisable",
  "claims_to_avoid": ["claims this category legally cannot make"]
}}

Rules:
- One value proposition only. An ad that argues four benefits argues none.
- The call to action must be a real instruction, not a slogan.
- Never invent regulatory approval, clinical evidence, or guaranteed outcomes.
"""
        decoded = await self._generate_json(prompt, expect_list=False)
        if not isinstance(decoded, dict) or not decoded:
            logger.warning("Ads strategist unavailable; using a premise-derived fallback brief.")
            decoded = {}

        def _text(key: str, default: str) -> str:
            value = str(decoded.get(key) or "").strip()
            return (value or default)[:400]

        brief: Dict[str, Any] = {
            "brand": _text("brand", "the product"),
            "product": _text("product", premise.strip()[:200] or "the product"),
            "audience": _text("audience", "the general viewer"),
            "value_proposition": _text(
                "value_proposition", "It solves the problem shown on screen."
            ),
            "tone": _text("tone", "clear, confident, warm"),
            "call_to_action": _text("call_to_action", "Learn more today.")[:120],
            "product_visual": _text("product_visual", ""),
            "runtime_seconds": runtime,
            "shot_count": total_clips,
        }
        avoid = decoded.get("claims_to_avoid")
        brief["claims_to_avoid"] = (
            [str(item)[:120] for item in avoid][:8] if isinstance(avoid, list) else []
        )

        # The brief itself is copy, so it passes through the same guard.
        flags: List[str] = []
        for key in ("value_proposition", "call_to_action", "product", "brand"):
            brief[key], hits = apply_ad_compliance(brief[key])
            flags.extend(hits)
        brief["compliance_flags"] = sorted(set(flags))
        return brief

    # -------------------------------------------------------------------------
    # Phase 2 - shot list
    # -------------------------------------------------------------------------

    async def generate_ad_shot_list(
        self,
        *,
        brief: Dict[str, Any],
        premise: str,
        characters: List[Dict[str, Any]],
        history: str,
        total_clips: int,
        clip_duration: int,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Write the shot list. Returns (shots, report).

        The report records compliance rewrites and whether the call to action had
        to be appended, so the Studio can show what was changed instead of
        presenting an edited script as the writer's original output.
        """
        names = [str(c.get("name")) for c in characters if c.get("name")]
        char_list = ", ".join(names)
        arc_lines = "\n".join(
            f"- Shot {i + 1}: {_arc_position(i, total_clips)}" for i in range(total_clips)
        )
        cta = str(brief.get("call_to_action") or "")
        prompt = f"""You are the REVERIE advertising creative director and continuity supervisor.
Write the shot list for a {total_clips * clip_duration}-second commercial.

CAMPAIGN BRIEF:
{json.dumps(brief, ensure_ascii=False, indent=2)}

PRODUCT PREMISE:
{premise}

TALENT NOTES FROM THE TABLE READ:
{history}

REQUIRED ARC - follow this position for each shot:
{arc_lines}

Return ONLY a JSON array with exactly {total_clips} shots. Each shot lasts
{clip_duration} seconds and must contain:
- "location": a specific visible location
- "drama_beat": present-tense, filmable action in ONE continuous shot
- "characters_involved": 0 to 3 exact names from [{char_list}]
- "dialogues": zero to two {{"character_name", "line"}} objects; each line <= 12 words
- "continuity": {{
    "environment_state": time/light to carry forward,
    "transition_from_previous": visual connection from the prior shot (empty for shot 1),
    "character_state_updates": [{{"character_name", "state_note"}}]
  }}

Hard rules:
- The product must stay visually identical in every shot it appears in.
- The FINAL shot must deliver this call to action on screen or in dialogue: "{cta}"
- Never state a benefit the brief does not support. No invented statistics, no
  regulatory approval, no guaranteed outcomes, no medical claims.
- One continuous shot per entry. No montage, no unrelated cutaway.
- Use only the supplied talent names. Never invent a person.
- Do not create more or fewer than {total_clips} shots.
"""
        shots = await self._generate_json(prompt, expect_list=True)
        report: Dict[str, Any] = {
            "planner": "ads_specialist",
            "compliance_flags": [],
            "compliance_rewrites": 0,
            "cta_appended": False,
        }
        if not isinstance(shots, list) or len(shots) == 0:
            logger.error(
                "Ads specialist returned invalid output, expected %s shots.", total_clips
            )
            return [], report

        if len(shots) != total_clips:
            logger.warning(
                "Ads specialist returned %s shots, expected %s — adjusting.",
                len(shots),
                total_clips,
            )
            if len(shots) > total_clips:
                # Trim excess shots, keep CTA-bearing last shot.
                shots = shots[:total_clips - 1] + [shots[-1]]
            else:
                # Pad by repeating the last shot with adjusted beat.
                while len(shots) < total_clips:
                    pad = dict(shots[-1])
                    pad["drama_beat"] = f"Continuation — {pad.get('drama_beat', '')}"
                    shots.append(pad)

        clean = self._scrub_shots(shots, report)
        self._enforce_cta(clean, cta, report)
        report["compliance_flags"] = sorted(set(report["compliance_flags"]))
        logger.info(
            "Ads shot list ready: %s shots, %s compliance rewrites, cta_appended=%s",
            len(clean),
            report["compliance_rewrites"],
            report["cta_appended"],
        )
        return clean, report

    # -------------------------------------------------------------------------
    # Compliance and CTA enforcement
    # -------------------------------------------------------------------------

    def _scrub_shots(self, shots: List[Any], report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Apply the claim guard to every beat and line of dialogue."""
        cleaned: List[Dict[str, Any]] = []
        for raw in shots:
            if not isinstance(raw, dict):
                continue
            shot = dict(raw)
            beat, hits = apply_ad_compliance(str(shot.get("drama_beat") or ""))
            if hits:
                report["compliance_rewrites"] += 1
                report["compliance_flags"].extend(hits)
            shot["drama_beat"] = _sanitise_prompt(beat)

            lines: List[Dict[str, str]] = []
            for entry in shot.get("dialogues") or []:
                if not isinstance(entry, dict):
                    continue
                text, line_hits = apply_ad_compliance(
                    str(entry.get("line") or entry.get("text") or "")
                )
                if line_hits:
                    report["compliance_rewrites"] += 1
                    report["compliance_flags"].extend(line_hits)
                speaker = str(entry.get("character_name") or entry.get("character") or "").strip()
                if text.strip():
                    lines.append(
                        {"character_name": speaker, "line": _sanitise_prompt(text)[:180]}
                    )
            shot["dialogues"] = lines[:2]
            cleaned.append(shot)
        return cleaned

    @staticmethod
    def _enforce_cta(
        shots: List[Dict[str, Any]], call_to_action: str, report: Dict[str, Any]
    ) -> None:
        """Guarantee the ad actually asks for the action.

        An ad that never states its call to action has failed at its only job, so
        this is verified rather than trusted. When the writer omitted it, the CTA
        is written into the final beat and the report records that it was
        appended.
        """
        cta = call_to_action.strip()
        if not shots or not cta:
            return
        needle = re.sub(r"[^a-z0-9 ]", "", cta.lower()).strip()
        final = shots[-1]
        haystack = " ".join(
            [str(final.get("drama_beat") or "")]
            + [str(line.get("line") or "") for line in final.get("dialogues") or []]
        ).lower()
        haystack = re.sub(r"[^a-z0-9 ]", "", haystack)
        # Match on distinctive words: an exact string match is too brittle,
        # because a writer legitimately rephrases punctuation and tense.
        keywords = [word for word in needle.split() if len(word) > 3]
        if keywords and sum(1 for word in keywords if word in haystack) >= max(
            1, len(keywords) // 2
        ):
            return
        final["drama_beat"] = (
            str(final.get("drama_beat") or "").rstrip(". ")
            + f'. The call to action appears on screen in clean type: "{cta}"'
        )[:1800]
        report["cta_appended"] = True

    # -------------------------------------------------------------------------
    # Model plumbing
    # -------------------------------------------------------------------------

    async def _generate_json(self, prompt: str, *, expect_list: bool) -> Any:
        """Request JSON with the same backoff discipline as the screenwriter."""
        for attempt in range(4):
            try:
                response = await self.model.generate_content_async(
                    prompt,
                    generation_config={"response_mime_type": "application/json"},
                )
                decoded = json.loads(response.text)
                if expect_list and not isinstance(decoded, list):
                    raise ValueError("Expected a JSON array of shots.")
                if not expect_list and not isinstance(decoded, dict):
                    raise ValueError("Expected a JSON object.")
                return decoded
            except ResourceExhausted as exc:
                if attempt == 3:
                    logger.error("Ads specialist quota exhausted: %s", exc)
                    return [] if expect_list else {}
                delay = 20 * (2**attempt)
                logger.warning("Ads specialist rate limited; retrying in %ss", delay)
                await asyncio.sleep(delay)
            except Exception as exc:
                if attempt == 3:
                    logger.error("Ads specialist output failed validation: %s", exc)
                    return [] if expect_list else {}
                logger.warning("Invalid ads output attempt %s: %s", attempt + 1, exc)
        return [] if expect_list else {}
