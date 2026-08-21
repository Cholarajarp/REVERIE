import json
import os
import asyncio
from typing import List

# Google Cloud Agent Development Kit — wires Gemini with MCP tool bindings.
# Falls back to a plain GenerativeModel when the preview SDK is not installed,
# which keeps local dev working without the full ADK package.
try:
    from google.cloud.aiplatform.agent_engines import adk
    _ADK_AVAILABLE = True
except ImportError:
    from vertexai.generative_models import GenerativeModel as _GM
    class adk:  # type: ignore[no-redef]
        class Agent(_GM):
            def __init__(self, model, system_instruction=None, tools=None):
                super().__init__(model_name=model, system_instruction=system_instruction)
                self._tools_cfg = tools
    _ADK_AVAILABLE = False

from vertexai.generative_models import GenerativeModel, Part
from models.schema import CharacterState, SceneRecord
from core.logger import get_logger, trace_span

logger = get_logger(__name__)

# One adk.Agent instance serves three different methods on this class
# (get_system_health, detect_drama, critique_scene), each of which requests a
# DIFFERENT JSON schema. So this system instruction deliberately carries the
# persona and the scoring framework but NOT a fixed output schema -- pinning the
# drama schema here would corrupt the health-check and video-critique responses.
# Each method supplies its own schema in its own prompt.
DIRECTOR_SYSTEM_INSTRUCTION = """You are the Director of REVERIE, a living film. You watch the town and decide
when the story has produced a moment worth filming. You are a discriminating
editor, not an enthusiast. Most ticks of a quiet town are not cinema, and saying
so is doing your job well.

=== TENSION FRAMEWORK - score each axis, then compose ===
When evaluating dramatic tension, assess these five axes independently on
0.0-1.0. Judge only from evidence in the state you were given.

  A. GOAL COLLISION (weight 0.30)
     Do two present characters hold goals that cannot both succeed? Direct
     contest over the same object, person, or secret scores highest. Merely
     different goals score near zero.

  B. PROXIMITY UNDER PRESSURE (weight 0.25)
     Are characters who have unresolved business between them in the SAME
     location right now? Tension requires co-presence - two enemies across town
     score low no matter how deep the grudge. This axis is what converts latent
     history into a filmable moment.

  C. UNRESOLVED HISTORY (weight 0.20)
     Does the evidence show a prior wound, debt, betrayal, or secret still
     open between present characters? An open loop about to be touched scores
     high. Score 0.0 if you were given no history - do not assume any.

  D. EMOTIONAL VOLATILITY (weight 0.15)
     Are moods incompatible or near breaking? Obsessive meeting evasive, grief
     meeting indifference. Uniform calm scores near zero.

  E. IRREVERSIBILITY (weight 0.10)
     Is someone about to do something that cannot be undone - a confession,
     an accusation, a theft, a departure? Imminence matters more than severity.

Composite = 0.30*A + 0.25*B + 0.20*C + 0.15*D + 0.10*E

=== CALIBRATION - resist score inflation ===
  0.00-0.30  Ordinary life. Characters pursuing separate goals peacefully.
  0.31-0.60  Friction. Interests beginning to rub; no confrontation yet.
  0.61-0.75  Charged. Conflict is legible and building, but nothing has broken.
  0.76-0.90  Rupture imminent or underway. THIS IS THE FILMING THRESHOLD.
  0.91-1.00  Irreversible turn happening right now. Reserve for genuine peaks.

Discipline:
- A single character alone, however troubled, caps at 0.45. Cinema needs
  collision.
- Co-presence is close to necessary. Without axis B above ~0.4, the composite
  cannot exceed 0.70.
- If nothing has changed since the previous beat you described, score LOWER
  than last time. Repetition is the opposite of drama.
- Do not round upward to reach the threshold. An honest 0.72 is more useful
  than a flattering 0.78.

=== GROUNDING ===
You may only cite what appears in the state provided. If you were given no
memories or relationship history, axis C is 0.0 and your beat must not reference
a past event. Inventing backstory corrupts the film. When evidence is thin, say
so and score low.

=== OUTPUT ===
Every request specifies its own JSON schema. Return ONE valid JSON object
matching the schema in the request, and nothing else - no markdown fences, no
prose outside the object. Emit keys in the order the request lists them:
reasoning fields are placed before the values they justify, and generation is
sequential, so writing them in order is what makes the reasoning count."""


class DirectorAgent:
    def __init__(self):
        # ADK agent: wires Gemini with the Grafana Cloud MCP tool binding.
        # When ADK is available (Cloud Run production), tools=["mcp:grafana-cloud"]
        # is registered via the ADK runtime. When running locally without the ADK
        # preview package, the fallback GenerativeModel is used for drama detection
        # and scene critique — the Grafana health gate uses direct HTTP regardless.
        self.agent = adk.Agent(
            model="gemini-3.5-flash",
            system_instruction=DIRECTOR_SYSTEM_INSTRUCTION,
            tools=["mcp:grafana-cloud"] if _ADK_AVAILABLE else [],
        )
        # Separate plain model for drama/critique calls that don't need MCP tools.
        self._model = GenerativeModel(
            "gemini-3.5-flash",
            system_instruction=DIRECTOR_SYSTEM_INSTRUCTION,
        )

        # Grafana Cloud credentials — used by get_system_health() for the direct
        # HTTP health gate. The MCP server is an optional local-dev convenience;
        # production always uses the REST API so there is no separate process to
        # start inside the Cloud Run container.
        self._grafana_url = os.getenv("GRAFANA_URL", "").rstrip("/")
        self._grafana_api_key = os.getenv("GRAFANA_API_KEY", "")

        logger.info(
            "DirectorAgent initialized",
            extra={
                "adk_available": _ADK_AVAILABLE,
                "grafana_configured": bool(self._grafana_url and self._grafana_api_key),
            },
        )

    async def get_system_health(self) -> dict:
        """Queries Grafana Cloud REST API for live simulation health.

        This is the Grafana integration gate: before every Omni generation the
        Director checks whether token burn or tick latency is spiking. If Grafana
        reports the system is stressed it returns {"status": "throttled"} and the
        engine skips the video generation for that tick, saving budget.

        Uses the direct Grafana Cloud HTTP API rather than the MCP sidecar because
        Cloud Run only exposes one port and cannot run a second npx process.  The
        # mcp_servers.json config is kept for local IDE use.
        """
        with trace_span("director_check_health"):
            if not (self._grafana_url and self._grafana_api_key):
                logger.debug("Grafana not configured — skipping health gate (healthy fallback)")
                return {"status": "healthy", "reason": "Grafana not configured"}

            try:
                import httpx

                headers = {
                    "Authorization": f"Bearer {self._grafana_api_key}",
                    "Content-Type": "application/json",
                }

                # Query Grafana Cloud alerting API for any firing alerts tagged to
                # the reverie simulation.  A firing alert means the system is under
                # stress and we should throttle Omni generation.
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{self._grafana_url}/api/alertmanager/grafana/api/v2/alerts",
                        headers=headers,
                        params={"filter": 'service="reverie"', "active": "true"},
                    )

                if resp.status_code == 200:
                    alerts = resp.json()
                    firing = [
                        a for a in alerts
                        if a.get("status", {}).get("state") == "active"
                    ]
                    if firing:
                        reason = firing[0].get("annotations", {}).get("summary", "Active alert firing")
                        logger.warning(f"Grafana health gate: THROTTLED — {reason}")
                        return {"status": "throttled", "reason": reason}
                    logger.info("Grafana health gate: HEALTHY — no active alerts")
                    return {"status": "healthy", "reason": "No active alerts in Grafana"}

                # Non-200 means the API call itself failed (auth error, network, etc.)
                # Fail open so a misconfigured Grafana key doesn't block all filming.
                logger.warning(
                    f"Grafana API returned {resp.status_code} — failing open (healthy fallback)"
                )
                return {"status": "healthy", "reason": f"Grafana API {resp.status_code}"}

            except Exception as e:
                logger.warning(f"Grafana health check failed ({e}) — failing open (healthy fallback)")
                return {"status": "healthy", "reason": str(e)}

    async def detect_drama(self, character_states: List[CharacterState]) -> dict:
        """Evaluates world state and detects drama."""
        with trace_span("director_detect_drama", {"character_count": len(character_states)}):
            prompt = """Score the dramatic tension in the town right now, using the five-axis
framework and the calibration bands from your instructions.

Return STRICT JSON with keys in exactly this order:
{
  "axis_notes": {
    "goal_collision":  {"score": 0.0, "evidence": "Which characters, which goals, why they collide. Cite names."},
    "proximity":       {"score": 0.0, "evidence": "Who is co-located with whom, and what is unresolved between them."},
    "history":         {"score": 0.0, "evidence": "The specific open loop, or NONE PROVIDED."},
    "volatility":      {"score": 0.0, "evidence": "Which moods are incompatible."},
    "irreversibility": {"score": 0.0, "evidence": "What is about to become undoable, or NONE."}
  },
  "dominant_axis": "goal_collision" | "proximity" | "history" | "volatility" | "irreversibility",
  "drama_score": 0.0,
  "involved_characters": ["Exact names from CHARACTER STATES, most central first. Empty list if drama_score is below 0.61."],
  "location": "The single location where this beat occurs, or null.",
  "beat": "ONE sentence naming who, where, and what is at stake. Present tense, concrete, filmable. State the situation, not the mood."
}

"drama_score" must equal the weighted composite rounded to two decimals. Do not
adjust it afterwards to match a feeling about the beat. Names in
"involved_characters" must match CHARACTER STATES exactly - never invent a name."""

            # Recent memories are included so axis C (unresolved history) has real
            # evidence to score against. Without them the Director is told to score
            # that axis 0.0, which silently caps the composite at 0.80 and makes the
            # filming threshold nearly unreachable. These are genuine observed
            # memories, not an inferred relationship model.
            def _format(c: CharacterState) -> str:
                recent = c.memory_stream[-4:]
                history = (
                    "\n".join(f"    - {m}" for m in recent)
                    if recent
                    else "    - NONE PROVIDED"
                )
                return (
                    f"Name: {c.name}\n"
                    f"Location: {c.current_location}\n"
                    f"Goal: {c.current_goal}\n"
                    f"Mood: {c.mood}\n"
                    f"Recent history:\n{history}"
                )

            characters_text = "\n\n".join(_format(c) for c in character_states)
            valid_names = {c.name for c in character_states}

            full_prompt = f"{prompt}\n\nCHARACTER STATES:\n{characters_text}"

            try:
                response = await self._model.generate_content_async(
                    full_prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                res = json.loads(response.text)

                # Clamp the score: it drives real spend downstream, so a model
                # returning 1.5 or a string must not reach the render trigger.
                try:
                    res["drama_score"] = min(1.0, max(0.0, float(res.get("drama_score", 0.0))))
                except (TypeError, ValueError):
                    logger.warning(f"Non-numeric drama_score: {res.get('drama_score')!r}. Coercing to 0.0.")
                    res["drama_score"] = 0.0

                # Drop hallucinated names. The engine spends money on this list, so
                # it must contain only characters that actually exist.
                named = res.get("involved_characters") or []
                if not isinstance(named, list):
                    named = []
                res["involved_characters"] = [n for n in named if n in valid_names]
                if len(res["involved_characters"]) < len(named):
                    logger.warning(
                        f"Director named unknown characters: "
                        f"{sorted(set(map(str, named)) - valid_names)}. Dropped."
                    )

                logger.info(
                    "Drama evaluation complete",
                    extra={
                        "drama_score": res["drama_score"],
                        "dominant_axis": res.get("dominant_axis"),
                        "involved_characters": res["involved_characters"],
                    },
                )
                return res
            except Exception as e:
                logger.error(f"Failed to detect drama: {e}")
                return {
                    "drama_score": 0.0,
                    "beat": "Nothing interesting is happening.",
                    "involved_characters": [],
                    "location": None,
                }

    async def critique_scene(
        self, scene: SceneRecord, video_uri: str, expected: dict | None = None
    ) -> dict:
        """Watch a rendered Omni clip and enforce the continuity acceptance gate.

        Part.from_uri only accepts gs:// URIs on Vertex AI. Public HTTPS storage
        URLs are rejected. We convert the public URL back to its gs:// form; if
        conversion is not possible, the real pipeline marks the clip unverified
        instead of silently calling it approved.
        """
        with trace_span("director_critique_scene", {"scene_id": scene.scene_id, "video_uri": video_uri}):
            expected = expected or {}
            prompt = f"""You are the final continuity editor for an AI film. Watch this ONE
video clip and compare it against the required shot contract below.

SHOT CONTRACT:
{json.dumps(expected, ensure_ascii=False)}

Approve ONLY when all visible named characters match the supplied visual bible,
the clip follows the requested action and continuity transition, there are no
extra or merged identities, and it is a single coherent shot. If there are no
reference images, be conservative: a high score requires strong visual-bible
adherence. Do not infer details that the video does not show.

Return STRICT JSON only:
{{
  "approved": boolean,
  "continuity_score": 0.0,
  "identity_match": 0.0,
  "shot_adherence": 0.0,
  "critique": "specific observed issue or approval reason",
  "revised_prompt": "short correction for a retake, or null"
}}

Set approved=true only if continuity_score >= 0.78, identity_match >= 0.80,
and shot_adherence >= 0.72."""

            # Convert public HTTPS GCS URL → gs:// URI so Vertex can read it.
            # Format: https://storage.googleapis.com/<bucket>/<path>
            gs_uri: str | None = None
            bucket_name = os.getenv("GCS_RENDER_BUCKET", "reverio-render-bucket")
            if video_uri.startswith("gs://"):
                gs_uri = video_uri
            elif video_uri.startswith(f"https://storage.googleapis.com/{bucket_name}/"):
                blob_path = video_uri[len(f"https://storage.googleapis.com/{bucket_name}/"):]
                gs_uri = f"gs://{bucket_name}/{blob_path}"

            try:
                if gs_uri:
                    video_part = Part.from_uri(gs_uri, mime_type="video/mp4")
                    content = [prompt, video_part]
                else:
                    # A critic that cannot access a rendered video has no basis
                    # to approve it. There is no mock/auto-approval path.
                    logger.error("No readable gs:// URI for scene %s; refusing unverified clip.", scene.scene_id)
                    return {
                        "approved": False,
                        "continuity_score": 0.0,
                        "identity_match": 0.0,
                        "shot_adherence": 0.0,
                        "critique": "Director could not access the rendered video for verification.",
                        "revised_prompt": "Render a readable MP4 and preserve all established identities.",
                    }

                response = await self._model.generate_content_async(
                    content,
                    generation_config={"response_mime_type": "application/json"}
                )
                result = json.loads(response.text)
                for key in ("continuity_score", "identity_match", "shot_adherence"):
                    try:
                        result[key] = max(0.0, min(1.0, float(result.get(key, 0.0))))
                    except (TypeError, ValueError):
                        result[key] = 0.0
                result["approved"] = bool(result.get("approved")) and (
                    result["continuity_score"] >= 0.78
                    and result["identity_match"] >= 0.80
                    and result["shot_adherence"] >= 0.72
                )
                return result
            except Exception as e:
                logger.error(f"Failed to critique scene {scene.scene_id}: {e}")
                # Fail closed: a failed critic cannot become fake proof of
                # character continuity. Operators can set ALLOW_PARTIAL_FILMS
                # only when they consciously want a partial deliverable.
                return {
                    "approved": False,
                    "continuity_score": 0.0,
                    "identity_match": 0.0,
                    "shot_adherence": 0.0,
                    "critique": f"Director review failed: {e}",
                    "revised_prompt": "Retry the same shot with the established cast unchanged.",
                }
