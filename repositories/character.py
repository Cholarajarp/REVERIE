from models.schema import CharacterState
from repositories.base import BaseRepository

class CharacterRepository(BaseRepository[CharacterState]):
    collection_name = "characters"
    model_class = CharacterState
