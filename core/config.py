import os
import logging
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

load_dotenv()

# Initialize OpenAI Client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Qdrant Cloud is used for the public demo. Localhost remains a fallback for dev.
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "evidence-locker")

_raw_vector_name = os.getenv("QDRANT_VECTOR_NAME", "").strip()
QDRANT_VECTOR_NAME = "" if _raw_vector_name in {"", "default", "empty/default"} else _raw_vector_name

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "1536"))

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)