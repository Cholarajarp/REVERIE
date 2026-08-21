from models.schema import WorldState
from repositories.base import BaseRepository

class WorldRepository(BaseRepository[WorldState]):
    collection_name = "worlds"
    model_class = WorldState
