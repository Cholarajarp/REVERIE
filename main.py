import os
import json
import asyncio
import base64
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from core.logger import get_logger
from core.clients import clients
from core.omni_pipeline import OmniPipeline
from core.video_editor import VideoEditor
from core.studio_engine import StudioEngine
from core.audience_sync import audience_websocket_endpoint, audience_sync_manager
from core.redis_broadcaster import RedisBroadcaster
from agents.cinematographer_agent import CinematographerAgent
from agents.factory import create_dynamic_characters
from repositories.world import WorldRepository
from repositories.scene import SceneRepository
from repositories.character import CharacterRepository
from models.schema import WorldState
from datetime import datetime

logger = get_logger(__name__)

class ReferenceAsset(BaseModel):
    """An uploaded image explicitly assigned to a cast member."""
    url: str
    label: str = ""
    type: str = "image"
    mime_type: str = ""


class CharacterConfig(BaseModel):
    name: str
    current_location: str = "Unknown"
    current_goal: str = "Exist"
    mood: str = "Neutral"
    memory_stream: List[str] = Field(default_factory=list)
    personality_description: str = ""
    # Stable visual description for Omni continuity. Describes age, appearance,
    # hair, and costume so every generated clip renders the same character.
    visual_description: str = ""
    # Retained for backwards-compatible saved presets only.
    # Omni generates native audio; Cloud TTS is not called by the studio path.
    voice_id: str = ""
    reference_image_base64: str = ""  # Base64-encoded character reference image
    # Only a labelled image is used as a subject anchor. Generic video/audio
    # assets are not silently passed to Omni, because that API does not support
    # audio references and unreliable video-reference behaviour would weaken the
    # continuity claim.
    reference_asset_urls: List[ReferenceAsset] = Field(default_factory=list)

class StartSimulationRequest(BaseModel):
    characters: List[CharacterConfig]
    video_duration: str = "10s"
    film_duration_minutes: int = 1
    aspect_ratio: str = "16:9"
    visual_style: str = "cinematic"
    premise: Optional[str] = None
    
class RenderScriptRequest(BaseModel):
    script: List[Dict]
    settings: Dict
    characters: List[Dict]
    # Carried through from simulate_script. Without it the render invents a new
    # production id, which changes every scene's stable seed and detaches the
    # rendered shots from the production they were planned as.
    production_id: str = ""

class GenerateCastRequest(BaseModel):
    premise: str  # e.g. "Spider-Man in 2050 fighting a cyber villain"
    num_characters: int = 3
    visual_style: str = "cinematic"
    film_duration_minutes: int = 1

# Global instances
studio_engine = None
broadcaster: Optional[RedisBroadcaster] = None
# Strong reference to the studio task
_studio_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and graceful shutdown.

    Uses the lifespan protocol rather than @app.on_event (deprecated) because
    shutdown ordering matters here: Cloud Run sends SIGTERM then SIGKILLs about
    10 seconds later, and the simulation lease must be released inside that
    window or a replacement instance waits out the full TTL before taking over.
    """
    global studio_engine, broadcaster

    logger.info("Initializing REVERIE backend services...")
    clients.init_vertex()

    # Authentication is handled via Vertex AI ADC on Cloud Run.

    # Cross-instance replication. Started BEFORE the first WebSocket is served,
    # because a client connecting to an un-hydrated instance would receive an
    # empty document and then watch the whole backlog appear.
    broadcaster = RedisBroadcaster(
        doc=audience_sync_manager.ydoc,
        on_remote_update=audience_sync_manager.deliver_remote_update,
    )
    audience_sync_manager.attach_broadcaster(broadcaster)
    try:
        await broadcaster.start()
    except Exception as e:
        # Degrade to single-instance rather than failing startup. A raised
        # exception here fails the container health check, and Cloud Run would
        # roll back the revision over what may be a transient Redis blip.
        logger.error(f"Broadcaster failed to start; serving single-instance: {e}")

    char_repo = CharacterRepository()
    world_repo = WorldRepository()
    scene_repo = SceneRepository()

    omni = OmniPipeline(scene_repo)
    # Uses Vertex AI ADC — no API key needed. Credentials come from the
    # Cloud Run service account automatically.
    omni.validate_configuration()
    cinematographer = CinematographerAgent()
    editor = VideoEditor()

    studio_engine = StudioEngine(
        cinematographer=cinematographer,
        omni=omni,
        editor=editor,
        scene_repo=scene_repo,
    )

    logger.info("Startup complete. REVERIE is ready.")

    yield

    # --- shutdown (SIGTERM on Cloud Run: ~10s before SIGKILL) ---
    logger.info("Shutting down REVERIE backend...")

    # StudioEngine does not hold persistent state across requests; cancel the
    # in-flight render task if one is running.
    if _studio_task and not _studio_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(_studio_task), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("Studio task did not stop in time; cancelling it.")
            _studio_task.cancel()
        except Exception as e:
            logger.debug(f"Studio task ended with: {e}")

    if broadcaster:
        # Releases the lease and closes the Redis connection. Doing this last
        # means the lock is freed even if the steps above timed out.
        await broadcaster.stop()

    logger.info("Shutdown complete.")


app = FastAPI(
    title="REVERIE Simulation Backend",
    description="Production-ready backend foundation for agentic simulations with enterprise security and observability.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for a separately-hosted local frontend. Cloud Run serves the static
# frontend from this app's origin, so production normally needs no extra origin.
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe.

    Deliberately returns 200 even when Redis is down. Cloud Run removes failing
    instances from the load balancer, so reporting unhealthy during a Memorystore
    blip would take down the entire fleet at once -- while each instance can
    still serve its own WebSockets correctly. The degraded state is reported in
    the body for observability instead.
    """
    return {
        "status": "ok",
        "instance_id": broadcaster.instance_id if broadcaster else None,
        "replication": "redis" if (broadcaster and broadcaster.enabled) else "single-instance",
        "is_simulation_leader": bool(broadcaster.is_leader) if broadcaster else None,
        "simulation_running": bool(_studio_task and not _studio_task.done()),
        "local_connections": len(audience_sync_manager.active_connections),
    }

# Global lock: prevents two concurrent simulate_script or generate_movie calls
# from saturating the same Gemini quota window simultaneously.
_simulate_lock = asyncio.Lock()

@app.post("/start_simulation", tags=["Simulation"])
async def start_simulation(request: StartSimulationRequest):
    """Requests that the movie studio generation begin."""
    global studio_engine, _studio_task

    if studio_engine is None:
        return {"status": "unavailable", "detail": "Engine still initializing"}

    if _studio_task and not _studio_task.done():
        return {"status": "already_running"}

    character_configs = [c.model_dump() for c in request.characters]
    
    # We pass the prompt/premise dynamically, or default to a generic one
    premise = "An intense dramatic confrontation between the characters."
    if hasattr(request, "premise") and request.premise:
        premise = request.premise

    _studio_task = asyncio.create_task(studio_engine.generate_movie(
        characters=character_configs,
        premise=premise,
        video_duration=request.video_duration,
        film_duration_minutes=request.film_duration_minutes,
        aspect_ratio=request.aspect_ratio,
        visual_style=request.visual_style
    ))

    def _log_completion(task: asyncio.Task) -> None:
        if task.cancelled():
            logger.info("Studio task was cancelled.")
            return
        exc = task.exception()
        if exc:
            logger.error(f"Studio task terminated with an exception: {exc}")
        else:
            logger.info(f"Studio task completed successfully! Result URI: {task.result()}")

    _studio_task.add_done_callback(_log_completion)
    return {"status": "started"}

@app.post("/api/studio/simulate_script", tags=["Studio"])
async def api_simulate_script(request: StartSimulationRequest):
    """Phase 1: Generates the script based on organic agent interaction."""
    global studio_engine
    if studio_engine is None:
        return {"status": "unavailable", "detail": "Engine still initializing"}

    # Reject concurrent requests immediately — two simultaneous simulate calls
    # would double the QPM against the same Gemini quota window, guaranteeing 429s.
    if _simulate_lock.locked():
        return {"status": "busy", "detail": "A script generation is already running. Please wait for it to finish."}

    async with _simulate_lock:
        character_configs = [c.model_dump() for c in request.characters]
        premise = request.premise or "An intense dramatic confrontation between the characters."

        # 1 tick = 1 Gemini call per agent. With 3 agents and a 12s gap that is
        # 3 calls spread over 24s — well under the 10 QPM quota limit.
        # The 30s screenwriting cooldown then lets the quota window fully reset.
        result = await studio_engine.simulate_script(
            characters=character_configs,
            premise=premise,
            video_duration=request.video_duration,
            film_duration_minutes=request.film_duration_minutes,
            aspect_ratio=request.aspect_ratio,
            visual_style=request.visual_style,
            simulation_ticks=1
        )
        return result

@app.post("/api/studio/render_movie", tags=["Studio"])
async def api_render_movie(request: RenderScriptRequest):
    """Phase 2: Renders an approved script into a full movie."""
    global studio_engine, _studio_task
    if studio_engine is None:
        return {"status": "unavailable", "detail": "Engine still initializing"}
        
    if _studio_task and not _studio_task.done():
        return {"status": "already_running"}
        
    _studio_task = asyncio.create_task(studio_engine.render_movie({
        "script": request.script,
        "settings": request.settings,
        "characters": request.characters,
        "production_id": request.production_id,
    }))
    
    def _log_completion(task: asyncio.Task) -> None:
        if task.cancelled():
            logger.info("Studio task was cancelled.")
            return
        exc = task.exception()
        if exc:
            logger.error(f"Studio task terminated with an exception: {exc}")
        else:
            logger.info(f"Studio task completed successfully! Result URI: {task.result()}")

    _studio_task.add_done_callback(_log_completion)
    return {"status": "started"}


@app.get("/api/debug/omni_test", tags=["Debug"])
async def debug_omni_test():
    """Non-billable health check for the Gemini Omni Flash harness.

    Reports configuration only — never creates a video.
    Auth uses Vertex AI ADC (service account on Cloud Run), no API key needed.
    """
    project_configured = bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
    bucket_configured = bool(os.getenv("GCS_RENDER_BUCKET"))
    renderer_ready = project_configured and bucket_configured
    return {
        "status": "ready" if renderer_ready else "misconfigured",
        "renderer": "gemini-omni-flash-preview",
        "model": os.getenv("OMNI_MODEL_ID", "gemini-omni-flash-preview"),
        "auth": "vertex_ai_adc",
        "gcp_project_configured": project_configured,
        "gcs_render_bucket_configured": bucket_configured,
        "continuity_mode": "accepted_interaction_chain",
        "detail": (
            "Ready to render through the Studio."
            if renderer_ready
            else "Set GOOGLE_CLOUD_PROJECT and GCS_RENDER_BUCKET."
        ),
    }


@app.post("/stop_simulation", tags=["Simulation"])
async def stop_simulation():
    """Stops the studio task if it is running."""
    global _studio_task

    if _studio_task and not _studio_task.done():
        _studio_task.cancel()
        return {"status": "stopping", "detail": "Studio task cancelled."}

    return {"status": "not_running", "detail": "Simulation was not running."}


@app.post("/api/studio/clear_scenes", tags=["Studio"])
async def clear_scenes():
    """Clear the Screening Room timeline without changing real Omni spend.

    The old endpoint reset the provider budget counter along with the scene
    documents. That made the UI show artificial capacity and defeated the daily
    safety limit. Clearing the display is safe; it must never mint more model
    generations.
    """
    try:
        scene_repo = SceneRepository()
        # Delete all scene documents
        await asyncio.to_thread(scene_repo.delete_all)
        logger.info("Cleared scene records; Omni budget counter intentionally preserved.")
        return {
            "status": "cleared",
            "detail": "All scene records deleted. Omni daily budget was preserved.",
        }
    except Exception as e:
        logger.error(f"Failed to clear scenes: {e}")
        return {"status": "error", "detail": str(e)}

@app.get("/api/studio/render_status", tags=["Studio"])
async def render_status():
    """Polls the current render task state and the number of scenes completed.

    The frontend uses this to show live render progress without holding an
    open HTTP connection for the full (potentially 30+ min) render duration.
    Returns:
        rendering_running  True while the render task is in progress.
        scenes_ready       Count of critiqued scenes with a video_uri.
        scenes_total       Total scenes attempted (any status).
        final_movie_uri    Filled when rendering_running=False and it completed.
    """
    is_running = bool(_studio_task and not _studio_task.done())
    final_uri: str | None = None
    error: str | None = None

    if _studio_task and _studio_task.done() and not _studio_task.cancelled():
        try:
            exc = _studio_task.exception()
            if exc:
                error = str(exc)
            else:
                result = _studio_task.result()
                if isinstance(result, str):
                    final_uri = result
        except Exception:
            pass

    try:
        scene_repo = SceneRepository()
        docs = scene_repo.db.collection(scene_repo.collection_name).stream()
        all_scenes = [doc.to_dict() for doc in docs]
        accepted = [
            s for s in all_scenes if s.get("status") == "critiqued" and s.get("video_uri")
        ]
        scenes_ready = len(accepted)
        # Split the accepted shots by how they were accepted. A single "ready"
        # count cannot distinguish a director-approved shot from one that merely
        # rendered, and the Screening Room must not present them as equivalent.
        scenes_approved = sum(
            1 for s in accepted if s.get("review_mode") == "director_approved"
        )
        scenes_unverified = scenes_ready - scenes_approved
        # Retakes create extra scene documents. Report screenplay shots rather
        # than attempts so 6 accepted scenes plus 2 rejected candidates is never
        # presented as an 8-clip film.
        scenes_total = max(
            (int(s.get("expected_scene_count") or 0) for s in all_scenes), default=0
        ) or len(all_scenes)
        generation_attempts = len(all_scenes)
    except Exception:
        scenes_ready = 0
        scenes_approved = 0
        scenes_unverified = 0
        scenes_total = 0
        generation_attempts = 0

    return {
        "rendering_running": is_running,
        "scenes_ready": scenes_ready,
        "scenes_approved": scenes_approved,
        "scenes_unverified": scenes_unverified,
        "review_mode": os.getenv("CONTINUITY_REVIEW_MODE", "advisory").strip().lower(),
        "scenes_total": scenes_total,
        "generation_attempts": generation_attempts,
        "final_movie_uri": final_uri,
        "error": error,
    }

@app.websocket("/ws/whispers")
async def websocket_whispers(websocket: WebSocket):
    user_id = f"viewer_{id(websocket)}"
    await audience_websocket_endpoint(websocket, user_id=user_id)

# ── Asset Upload ─────────────────────────────────────────────────────────────

# Allowed MIME types for reference assets. Broadened to common video/audio
# containers in addition to images so users can attach mood boards, voice
# samples, or short reference clips for reverie to build from.
_ALLOWED_ASSET_TYPES = {
    # Images
    "image/jpeg", "image/png", "image/webp", "image/gif",
    # Video reference clips
    "video/mp4", "video/webm", "video/quicktime",
    # Audio mood reference
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg",
}
_MAX_ASSET_BYTES = 20 * 1024 * 1024  # 20 MB per asset


@app.post("/api/studio/upload_asset", tags=["Studio"])
async def upload_asset(
    file: UploadFile = File(...),
    asset_type: str = Form("image"),  # "image" | "video" | "audio"
    label: str = Form(""),            # Optional human label (e.g. character name)
):
    """Upload a production asset.

    In the active continuity harness, only a PNG/JPEG/WebP image labelled with
    the exact cast-member name becomes an Omni subject reference. Audio and
    video assets remain in the production library; they are not falsely passed
    to Omni as reference inputs.

    The file is stored in GCS under ``assets/<uuid>.<ext>`` and the public URL
    plus base64 thumbnail (images only) are returned so the frontend can show
    a preview without a second round-trip.

    Returns:
        asset_id      Stable identifier — pass back in the render request.
        public_url    GCS public URL for the raw file.
        thumbnail_b64 Base64 data-URI for image thumbnails (empty for video/audio).
        mime_type     Echo of the detected MIME type.
        label         Echo of the caller-supplied label.
    """
    if file.content_type not in _ALLOWED_ASSET_TYPES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{file.content_type}'. "
                   f"Allowed: {sorted(_ALLOWED_ASSET_TYPES)}",
        )

    raw = await file.read()
    if len(raw) > _MAX_ASSET_BYTES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=413,
            detail=f"Asset too large ({len(raw) // 1024} KB). Maximum is 20 MB.",
        )

    ext = (file.filename or "asset").rsplit(".", 1)[-1].lower() or "bin"
    asset_id = uuid.uuid4().hex[:12]
    blob_name = f"assets/{asset_id}.{ext}"

    try:
        from google.cloud import storage as gcs
        storage_client = gcs.Client()
        bucket_name = os.getenv("GCS_RENDER_BUCKET", "reverio-render-bucket")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(raw, content_type=file.content_type)
        public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    except Exception as e:
        logger.error(f"Asset upload to GCS failed: {e}")
        # Fallback: return base64 data URI so the frontend still gets a preview
        # even when GCS is unavailable (local dev without credentials).
        public_url = f"data:{file.content_type};base64,{base64.b64encode(raw).decode()}"

    # Build a lightweight thumbnail data-URI for image assets only.
    thumbnail_b64 = ""
    if file.content_type.startswith("image/"):
        # Return the raw bytes as the thumbnail — the frontend already has them
        # via the upload, so we only need the data-URI for the preview card.
        thumbnail_b64 = f"data:{file.content_type};base64,{base64.b64encode(raw).decode()}"

    logger.info(
        f"Asset uploaded: id={asset_id} type={file.content_type} "
        f"size={len(raw)//1024}KB label='{label}'"
    )
    return {
        "asset_id": asset_id,
        "public_url": public_url,
        "thumbnail_b64": thumbnail_b64,
        "mime_type": file.content_type,
        "asset_type": asset_type,
        "label": label,
        "size_kb": len(raw) // 1024,
    }


@app.post("/generate_cast", tags=["Studio"])
async def generate_cast(request: GenerateCastRequest):
    """AI-powered cast generation from a one-line premise using Gemini."""
    from vertexai.generative_models import GenerativeModel

    model = GenerativeModel("gemini-3.5-flash")

    prompt = f"""You are a world-class screenwriter and casting director. Given a premise,
generate exactly {request.num_characters} detailed characters for an autonomous AI simulation.
The simulation will generate a {request.film_duration_minutes}-minute film in the "{request.visual_style}" visual style.
Tailor the character depth, goals, and conflicts to this duration. A 1-minute film needs immediate,
simple conflicts. A 10-minute film needs deeper, slow-burn tension.

Premise: "{request.premise}"
Visual Style: {request.visual_style}
Film Duration: {request.film_duration_minutes} minutes

For EACH character, output:
- name: A memorable, specific character name
- current_location: Where they start (a specific place name consistent with the premise)
- current_goal: Their immediate objective (1 sentence, active voice)
- mood: Their emotional state (2-3 descriptive words)
- personality_description: A detailed system prompt (3-4 sentences) describing who they are,
  how they speak, their motivations, and what makes them dramatically interesting
- memory_stream: An array of 4-5 first-person memories that establish their backstory
- visual_description: A concise but precise physical description for a video generation model
  (20-40 words). Include: age range, gender presentation, hair colour and style, distinctive
  facial features, and full costume/clothing appropriate to the premise and visual style.
  This description will be injected verbatim into EVERY video prompt so the character looks
  the same in every scene — be specific and consistent.
  Example: "Woman, mid-30s, sharp cheekbones, short silver hair, wearing a black trench coat
  and leather gloves, steely grey eyes"

IMPORTANT RULES:
- Characters MUST have conflicting goals that create dramatic tension
- At least 2 characters should start in the SAME location for immediate interaction
- Include at least one antagonist or morally ambiguous character
- Memories should hint at secrets, grudges, or unresolved relationships between characters
- visual_description must be in the aesthetic of the "{request.visual_style}" style
  (e.g. for "noir": period clothing, high-contrast lighting clues; for "anime": stylised features)

Return STRICT JSON array. No markdown. No explanation. Just the array."""

    try:
        response = await model.generate_content_async(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        characters = json.loads(response.text)

        logger.info(f"Generated {len(characters)} characters from premise: {request.premise[:60]}")
        return {"characters": characters}
    except Exception as e:
        logger.error(f"Cast generation failed: {e}")
        return {"characters": [], "error": str(e)}

@app.get("/api/scenes", tags=["Studio"])
async def list_scenes():
    """Returns all generated scene records for the screening room playlist."""
    try:
        scene_repo = SceneRepository()
        scenes_ref = scene_repo.db.collection(scene_repo.collection_name)
        docs = scenes_ref.order_by("scene_id").stream()
        scenes = []
        for doc in docs:
            data = doc.to_dict()
            # Return whichever prompt field is populated (omni_prompt for Studio Engine,
            # veo_prompt for SimulationEngine). Fall back to the other if one is empty.
            prompt = data.get("omni_prompt") or data.get("veo_prompt", "")
            scenes.append({
                "scene_id": data.get("scene_id", doc.id),
                "video_uri": data.get("video_uri", ""),
                "status": data.get("status", "unknown"),
                # Nullable on purpose: None means the writer scored no tension for
                # this beat. Defaulting to 0.0 would render as a confident "0%".
                "drama_score": data.get("drama_score"),
                "characters_involved": data.get("characters_involved", []),
                "veo_prompt": prompt,
                "omni_prompt": prompt,
                # Review metadata is surfaced so the Screening Room shows
                # evidence for continuity instead of only a green status dot.
                "continuity_score": data.get("continuity_score"),
                # How the shot was accepted. Without this the UI cannot tell an
                # approved shot from one that merely rendered, which is what let
                # the old build label every clip "director-approved".
                "review_mode": data.get("review_mode", "unverified"),
                # True only when the renderer accepted the parent interaction.
                # A non-empty previous_interaction_id is NOT proof of a chain:
                # it is written before the API call is attempted.
                "stateful_chain_verified": bool(data.get("stateful_chain_verified", False)),
                "scene_asset_labels": data.get("scene_asset_labels", []),
                "critique": data.get("critique", ""),
                "failure_reason": data.get("failure_reason", ""),
                "anchor_names": data.get("anchor_names", []),
                "previous_interaction_id": data.get("previous_interaction_id", ""),
                "omni_interaction_id": data.get("omni_interaction_id", ""),
                "generation_attempt": data.get("generation_attempt", 1),
                "scene_index": data.get("scene_index", 0),
                "expected_scene_count": data.get("expected_scene_count", 0),
                "actual_duration_seconds": data.get("actual_duration_seconds"),
            })
        return {"scenes": scenes, "total": len(scenes)}
    except Exception as e:
        logger.error(f"Failed to list scenes: {e}")
        return {"scenes": [], "total": 0, "error": str(e)}

# ── Serve Next.js Frontend (production only) ─────────────────────
# In Docker / Cloud Run the static export is at /app/frontend-out (output:"export").
# next.config.ts sets trailingSlash:true so every route becomes a directory with
# an index.html — client-side navigation works without a Node server.
# Mount LAST so all FastAPI API routes take priority.
_frontend_dir = os.path.join(os.path.dirname(__file__), "frontend-out")
if os.path.isdir(_frontend_dir):
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """Catch-all: serve Next.js static export for all non-API paths."""
        # Exact file match (JS bundles, images, etc.)
        exact = os.path.join(_frontend_dir, full_path)
        if os.path.isfile(exact):
            return FileResponse(exact)
        # Directory with index.html (trailingSlash routes like /studio/ → /studio/index.html)
        index_in_dir = os.path.join(_frontend_dir, full_path, "index.html")
        if os.path.isfile(index_in_dir):
            return FileResponse(index_in_dir)
        # Root fallback
        root_index = os.path.join(_frontend_dir, "index.html")
        if os.path.isfile(root_index):
            return FileResponse(root_index)
        return HTMLResponse("<h1>REVERIE</h1><p>Frontend not built. Run npm run build in reverie-frontend/</p>", status_code=200)
else:
    @app.get("/")
    async def get_root():
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
            <head><title>REVERIE API</title></head>
            <body>
                <h1>REVERIE Backend API</h1>
                <p>Frontend not mounted. Visit <a href="/docs">/docs</a> for API explorer.</p>
            </body>
        </html>
        """)
