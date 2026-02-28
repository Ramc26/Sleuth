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

# Initialize Qdrant Client (Uses local disk storage so data persists between runs)
# Using FastEmbed for lightning-fast, free local embeddings
# qdrant_client = QdrantClient(path="./qdrant_db") 

qdrant_client = QdrantClient(url="http://localhost:6333")
COLLECTION_NAME = "evidence_locker"