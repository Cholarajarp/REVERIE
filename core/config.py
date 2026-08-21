import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    REGION = os.getenv("GOOGLE_CLOUD_LOCATION", os.getenv("GOOGLE_CLOUD_REGION", "us-central1"))

config = Config()
