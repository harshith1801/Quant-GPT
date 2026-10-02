FROM node:22-alpine AS frontend
WORKDIR /build
RUN npm install -g pnpm@11.19.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/home/user HF_HOME=/home/user/.cache/huggingface PORT=7860 PINECONE_INDEX_NAME=finsight-index-v2
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt
COPY --chown=user:user backend/ ./backend/
COPY --chown=user:user query_engine.py filing_retrieval.py answer_grounding.py market_data.py ./
COPY --from=frontend --chown=user:user /build/dist ./frontend/dist
USER user
EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-7860}"]
