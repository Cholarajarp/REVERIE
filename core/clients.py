from google.cloud import firestore
import vertexai
from core.config import config
from core.logger import get_logger

logger = get_logger(__name__)

class Clients:
    _firestore_client = None
    _vertex_initialized = False

    @classmethod
    def get_firestore(cls) -> firestore.Client:
        if cls._firestore_client is None:
            logger.info("Initializing Firestore client via ADC")
            # Uses Application Default Credentials (ADC)
            cls._firestore_client = firestore.Client(project=config.PROJECT_ID)
        return cls._firestore_client

    @classmethod
    def init_vertex(cls):
        if not cls._vertex_initialized:
            logger.info("Initializing Vertex AI client via ADC")
            vertexai.init(project=config.PROJECT_ID, location=config.REGION)
            cls._vertex_initialized = True

clients = Clients()
