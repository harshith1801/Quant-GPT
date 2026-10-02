---
title: Quant GPT
emoji: 📊
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
---

# Quant GPT

A financial intelligence workspace that connects verified claims to original SEC filing evidence. React provides the research interface; FastAPI calls the existing Python retrieval, grounding, Alpha Vantage and caching functions. All provider keys remain on the server.

## Run locally

Python 3.12+ and Node 22+ are recommended. Configure `.env` from `.env.example` with your own credentials. The default API index is `finsight-index-v2`; it currently contains the validated AAPL dataset. Other companies can have market data without filing evidence. Missing evidence is reported explicitly.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install -g pnpm@11.19.0
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. For frontend development, run `pnpm dev` in `frontend/` alongside FastAPI. Vite proxies `/api` to port 8000. Production serves the frontend and API from one origin.

The first research request loads the existing embedding model. Model download may require internet access. Alpha Vantage daily closes are cached for six hours and news for two hours. Quotes show their actual trading date, not a claim of live pricing. The API keeps analysis jobs in memory for one hour, limits active jobs to two, and retains at most 64 jobs. Run one server worker for this local/single-container setup. This is a research application, not trading advice.

## Docker / Hugging Face

```sh
docker build -t quant-gpt .
docker run --rm --env-file .env -p 7860:7860 quant-gpt
```

The Docker image builds React, serves it with FastAPI on port 7860, and runs as user 1000. Add `GROQ_API_KEY`, `PINECONE_API_KEY`, and `ALPHA_VANTAGE_KEY` as **Space secrets**, and optionally `PINECONE_INDEX_NAME` as a server variable. `.env`, filings, and local caches are excluded from the image. No deployment has been performed. Public hosting needs access/quota policies appropriate to its audience; free API quotas are limited.

## Structure

- `frontend/`: React + TypeScript + Vite, custom CSS tokens, Motion, Lightweight Charts, locally bundled IBM Plex fonts.
- `backend/api.py`: HTTP adapter, job lifecycle, same-origin static serving.
- `backend/presentation.py`: lossless conversion of existing cited answers into displayable claims.
- `query_engine.py`, `filing_retrieval.py`, `answer_grounding.py`, `market_data.py`: validated Python services, preserved.
- `app.py`: previous Streamlit interface, retained as a fallback. It is not the new production entry point.
- `1_data_collection.py`, `2_processing.py`, `4_upload_to_pinecone.py`: SEC ingestion tools, unchanged by the frontend migration.
- `tests/`: offline regression tests for ingestion, retrieval, grounding, market data, and API presentation.
- `3_vector_db.py`: legacy Chroma experiment, retained for reference; not part of the current Pinecone pipeline or runtime dependencies.
- `docs/design.md`: design references, rationale, interaction and accessibility decisions.

## Checks

```sh
python -m unittest discover -s tests
cd frontend && pnpm build
```

These tests do not upload data or require live provider requests. Live analysis uses the configured provider quotas. The old Streamlit fallback disables file watching to avoid lazy Transformers vision-module imports; restart it manually after edits.
