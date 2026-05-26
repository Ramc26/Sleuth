# Sleuth Technical Notes

Sleuth is a FastAPI RAG demo for financial forensics.

## Core Flow

1. `POST /api/index_db` reads `.txt` evidence from `data/demo_data/evidence`.
2. `core/vector_store.py` embeds each evidence document with OpenAI `text-embedding-3-small`.
3. The app upserts 1536-dimensional vectors into Qdrant Cloud collection `evidence-locker`.
4. `POST /api/reconcile` compares two ledger CSV files.
5. `POST /api/investigate` embeds the case query, retrieves relevant evidence from Qdrant, and asks GPT-4o for a forensic report.

## Important Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, UI route, audit APIs |
| `core/config.py` | OpenAI and Qdrant Cloud config |
| `core/vector_store.py` | Evidence embedding, indexing, semantic retrieval |
| `core/investigator.py` | GPT-4o forensic report prompt |
| `templates/index.html` | Browser UI |
| `static/js/app.js` | Reconciliation and investigation UI behavior |
| `api/index.py` | Vercel entrypoint |

## Qdrant Collection

```text
Name: evidence-locker
Vector size: 1536
Distance: Cosine
Vector name: leave blank/default
```

## Environment

```env
OPENAI_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=evidence-locker
QDRANT_VECTOR_NAME=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

Zoho integration is disabled for the public demo.
