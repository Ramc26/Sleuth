# Sleuth — AI Financial Forensics

Sleuth is a deployed AI audit demo. Upload two ledger CSVs, identify variances, retrieve supporting evidence from Qdrant Cloud, and generate a forensic investigation report with GPT-4o.

## Demo Flow

1. Click **Sync Evidence Base** to embed bundled evidence from `data/demo_data/evidence`.
2. Upload two ledger CSVs in the Variance Analysis screen.
3. Click **Open Case** on a discrepancy.
4. Sleuth searches Qdrant Cloud and generates a structured forensic report.

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, Python 3.12 |
| UI | HTML, CSS, jQuery |
| LLM | OpenAI GPT-4o |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector DB | Qdrant Cloud |
| Deployment | Vercel Python runtime |

## Environment

Create `.env` locally or set these in Vercel:

```env
OPENAI_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=evidence-locker
QDRANT_VECTOR_NAME=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

The expected Qdrant collection is:

```text
Name: evidence-locker
Vector size: 1536
Distance: Cosine
Vector name: leave blank/default
```

## Local Run

```bash
uv sync
uv run uvicorn main:app --reload
```

Open `http://localhost:8000` for the landing page.

Live demo app: `http://localhost:8000/sleuth-2604`

## Vercel Deploy

```bash
vercel --prod
```

After deploy, seed Qdrant once:

```bash
curl -X POST https://your-vercel-app.vercel.app/api/index_db
```

Expected response:

```json
{
  "status": "success",
  "indexed_count": 12,
  "message": "Evidence locker synced successfully (12 files)."
}
```

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/api/health` | Qdrant status |
| `POST` | `/api/index_db` | Embed and upsert evidence files |
| `POST` | `/api/reconcile` | Compare two ledger CSVs |
| `POST` | `/api/investigate` | Run RAG forensic investigation |

## Input Data

Ledger CSVs must include:

```text
invoice_id,entity,date,amount
```

Evidence files are loaded from:

```text
data/demo_data/evidence/**/*.txt
```

## Notes

Zoho integration is disabled for this public demo. The deployed app focuses on evidence loading, embedding generation, audit sheet reconciliation, and AI forensic reporting.
