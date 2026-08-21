from datetime import datetime
from typing import List, Dict, Literal, Optional
from pydantic import BaseModel, Field

class CharacterState(BaseModel):
    name: str
    current_location: str
    current_goal: str
    mood: str
    memory_stream: List[str] = Field(default_factory=list)
    # Stable visual identity injected into every Omni prompt so the same character
    # looks the same in every clip.  Set at cast-creation time and never mutated
    # by the simulation loop.
    visual_description: str = ""

class WorldState(BaseModel):
    current_time: datetime
    weather: str
    active_characters: List[str] = Field(default_factory=list)
    location_populations: Dict[str, int] = Field(default_factory=dict)

class SceneRecord(BaseModel):
    scene_id: str
    characters_involved: List[str] = Field(default_factory=list)
    # The writer's tension rating for this specific beat, 0.0-1.0.
    # None means no rating was produced. It is deliberately nullable: the earlier
    # build derived this from scene_index / total_scenes, so the displayed
    # "drama" figure was really just a progress bar.
    drama_score: Optional[float] = None
    veo_prompt: str = ""
    omni_prompt: str = ""
    video_uri: str
    # ``video_uri`` is the browser-facing URL.  Keep the internal GCS path
    # separately so the editor and visual critic do not depend on a bucket
    # being publicly readable.
    storage_uri: str = ""
    audio_urls: List[str] = Field(default_factory=list)
    duration_seconds: int = 8
    resolution: str = "720p"
    aspect_ratio: str = "16:9"
    status: Literal['queued', 'rendering', 'critiqued', 'failed']
    # Continuity and review metadata are first-class evidence of the product's
    # value; a URL alone is not proof that a generated shot was accepted.
    # ``review_mode`` records HOW this shot was accepted so the UI can never
    # present an unreviewed clip as director-approved:
    #   director_approved  - the visual critic watched it and passed it
    #   unverified         - it rendered, but no critic verdict was obtained
    #   review_disabled    - the operator turned the gate off for this run
    review_mode: Literal['director_approved', 'unverified', 'review_disabled'] = 'unverified'
    seed: Optional[int] = None
    production_id: str = ""
    scene_index: int = 0
    expected_scene_count: int = 0
    anchor_image_uris: List[str] = Field(default_factory=list)
    continuity_score: Optional[float] = None
    actual_duration_seconds: Optional[float] = None
    critique: str = ""
    generation_attempt: int = 1
    failure_reason: str = ""
    # Omni-specific state. The next scene may only branch from a clip that the
    # Director accepted, which is what prevents independent-shot character drift.
    omni_interaction_id: str = ""
    previous_interaction_id: str = ""
    anchor_names: List[str] = Field(default_factory=list)
    # True only when the renderer actually accepted a parent interaction id.
    # The UI must not claim a stateful chain from a non-empty parent field alone,
    # because the parent is recorded before the API call is attempted.
    stateful_chain_verified: bool = False
    # Per-scene media the user attached to THIS shot in the script editor,
    # separate from the per-character cast locks.
    scene_asset_labels: List[str] = Field(default_factory=list)
