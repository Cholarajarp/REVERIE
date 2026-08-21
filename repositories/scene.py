from datetime import datetime
import asyncio
from google.cloud import firestore
from models.schema import SceneRecord
from repositories.base import BaseRepository
from core.logger import get_logger

logger = get_logger(__name__)

class BudgetExceededError(Exception):
    pass

class SceneRepository(BaseRepository[SceneRecord]):
    collection_name = "scenes"
    model_class = SceneRecord

    async def _reserve_generation_budget(
        self,
        scene_id: str,
        scene: SceneRecord,
        budget_document: str,
        provider_name: str,
        daily_limit: int = 24,
    ) -> SceneRecord:
        """Atomically reserve one provider generation before an API call.

        Uses a plain read-then-write inside a sync function run in an executor,
        avoiding the @firestore.transactional decorator which is incompatible
        with asyncio.to_thread (the decorator itself returns a coroutine that
        cannot be called from a thread executor).
        """
        budget_ref = self.db.collection("system_meta").document(budget_document)
        scene_ref = self.get_ref(scene_id)
        scene_dict = scene.model_dump(mode="json")

        def _do_reserve():
            now_date = datetime.utcnow().strftime("%Y-%m-%d")
            # Simple optimistic write — good enough for single-instance Cloud Run
            # (max-instances=1 in cloudbuild.yaml so no concurrent writes).
            snapshot = budget_ref.get()
            count = 0
            if snapshot.exists:
                snap_dict = snapshot.to_dict() or {}
                if snap_dict.get("date") == now_date:
                    count = int(snap_dict.get("count", 0))

            if count >= daily_limit:
                raise BudgetExceededError(
                    f"Daily budget of {daily_limit} clips reached ({count} used today)."
                )

            budget_ref.set({"date": now_date, "count": count + 1}, merge=True)
            scene_ref.set(scene_dict, merge=True)
            return count + 1

        try:
            await asyncio.to_thread(_do_reserve)
            logger.info(f"Reserved {provider_name} budget and queued scene {scene_id}.")
            return scene
        except BudgetExceededError:
            raise
        except Exception as e:
            logger.error(f"Failed {provider_name} budget reservation for {scene_id}: {e}")
            raise

    async def reserve_omni_budget(
        self, scene_id: str, scene: SceneRecord, daily_limit: int = 24
    ) -> SceneRecord:
        """Reserve a Gemini Omni Flash generation against the Omni counter."""
        return await self._reserve_generation_budget(
            scene_id, scene, "omni_budget", "Omni", daily_limit
        )

    async def reserve_veo_budget(self, scene_id: str, scene: SceneRecord) -> SceneRecord:
        """Compatibility path for the legacy Veo experiment."""
        return await self._reserve_generation_budget(
            scene_id, scene, "veo_budget", "Veo"
        )
