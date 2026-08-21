from typing import TypeVar, Generic, Optional, Type
from pydantic import BaseModel
from google.cloud.firestore import Client, DocumentReference

from core.clients import clients

T = TypeVar('T', bound=BaseModel)

class BaseRepository(Generic[T]):
    collection_name: str
    model_class: Type[T]

    def __init__(self):
        self.db: Client = clients.get_firestore()

    def get_ref(self, doc_id: str) -> DocumentReference:
        return self.db.collection(self.collection_name).document(doc_id)

    def get(self, doc_id: str) -> Optional[T]:
        doc = self.get_ref(doc_id).get()
        if doc.exists:
            return self.model_class.model_validate(doc.to_dict())
        return None

    def save(self, doc_id: str, data: T) -> None:
        # Use MERGE to prevent overwriting concurrent updates
        self.get_ref(doc_id).set(data.model_dump(mode='json'), merge=True)

    def delete(self, doc_id: str) -> None:
        self.get_ref(doc_id).delete()

    def delete_all(self) -> None:
        """Deletes all documents in this collection."""
        docs = self.db.collection(self.collection_name).stream()
        for doc in docs:
            doc.reference.delete()
