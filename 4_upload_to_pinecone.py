"""Validate prepared SEC chunks locally; upload only with an explicit --upload flag."""

import argparse
from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv

DEFAULT_INPUT = Path(__file__).resolve().parent / "processed_chunks_CLEAN.json"
INDEX_NAME = "finsight-index"


def validate_chunks(chunks):
    """Reject legacy/colliding IDs or incomplete provenance before any API call."""
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("Expected a non-empty list of processed chunks.")
    seen = set()
    filing_metadata = {}
    numbers = defaultdict(set)
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("Every chunk must be an object.")
        for field in ("chunk_id", "content", "ticker", "filing_type", "filing_date",
                      "accession_number", "source", "document_name"):
            if not isinstance(chunk.get(field), str) or not chunk[field].strip():
                raise ValueError(f"Chunk is missing a non-empty {field}.")
        ticker, form, accession = chunk["ticker"], chunk["filing_type"], chunk["accession_number"]
        if not re.fullmatch(r"[A-Z0-9.-]+", ticker) or form not in {"10-K", "10-Q"}:
            raise ValueError("Invalid ticker or filing type.")
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise ValueError("Invalid SEC accession number.")
        if date.fromisoformat(chunk["filing_date"]).isoformat() != chunk["filing_date"]:
            raise ValueError("Filing date must be YYYY-MM-DD.")
        if "report_date" in chunk:
            date.fromisoformat(chunk["report_date"])
        source = Path(chunk["source"])
        expected_path = ("sec-edgar-filings", ticker, form, accession, "full-submission.txt")
        if source.parts != expected_path:
            raise ValueError("Source path disagrees with the filing metadata.")
        number = chunk.get("chunk_number")
        if type(number) is not int or number < 0:
            raise ValueError("Chunk number must be a non-negative integer.")
        expected_id = f"{ticker}_{form}_{accession}_{number:05d}"
        if chunk["chunk_id"] != expected_id or expected_id in seen:
            raise ValueError("Duplicate or non-deterministic chunk ID; reprocess filings.")
        seen.add(expected_id)
        identity = (ticker, form, accession)
        provenance = (chunk["filing_date"], chunk.get("report_date"), chunk["source"], chunk["document_name"])
        if identity in filing_metadata and filing_metadata[identity] != provenance:
            raise ValueError("Conflicting metadata within a filing.")
        filing_metadata[identity] = provenance
        numbers[identity].add(number)
    for sequence in numbers.values():
        if sequence != set(range(len(sequence))):
            raise ValueError("Non-contiguous chunk numbers; the dataset may be incomplete.")
    return len(filing_metadata)


def vector_metadata(chunk):
    fields = ("ticker", "filing_type", "filing_date", "report_date", "accession_number",
              "source", "document_name", "chunk_number", "content")
    return {field: chunk[field] for field in fields if field in chunk}


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--upload", action="store_true", help="Write validated chunks to Pinecone")
    parser.add_argument("--index-name", default=os.getenv("PINECONE_INDEX_NAME", INDEX_NAME))
    parser.add_argument("--create-index", action="store_true", help="Create a missing serverless index")
    parser.add_argument("--require-empty", action="store_true", help="Refuse an index that contains data")
    parser.add_argument("--ticker", help="Require every input chunk to belong to this ticker")
    args = parser.parse_args()
    chunks = json.loads(args.input.read_text(encoding="utf-8"))
    filings = validate_chunks(chunks)
    if args.ticker and any(chunk["ticker"] != args.ticker.upper() for chunk in chunks):
        raise ValueError("The input contains an unexpected ticker.")
    print(f"Validated {len(chunks)} unique chunks from {filings} filings.")
    if not args.upload:
        print("Local validation only. No model was loaded and no Pinecone request was made.")
        return

    # Importing this module or validating a file never connects or uploads.
    from pinecone import Pinecone, ServerlessSpec
    from sentence_transformers import SentenceTransformer
    from tqdm import tqdm

    load_dotenv()
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY is required for upload.")
    pc = Pinecone(api_key=api_key)
    if args.index_name not in pc.list_indexes().names():
        if not args.create_index:
            raise ValueError("Target index does not exist; explicitly request --create-index.")
        pc.create_index(
            name=args.index_name, dimension=384, metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"), timeout=60,
        )
    description = pc.describe_index(args.index_name)
    if description.dimension != 384 or description.metric != "cosine":
        raise ValueError("Existing index must use 384 dimensions and cosine similarity.")
    if not description.status.ready:
        raise ValueError("Existing index is not ready.")
    index = pc.Index(args.index_name)
    if args.require_empty and index.describe_index_stats().total_vector_count:
        raise ValueError("Target index is not empty; refusing to overwrite existing data.")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    uploaded = 0
    for start in tqdm(range(0, len(chunks), 100)):
        batch = chunks[start:start + 100]
        embeddings = model.encode([chunk["content"] for chunk in batch]).tolist()
        vectors = [(chunk["chunk_id"], embedding, vector_metadata(chunk))
                   for chunk, embedding in zip(batch, embeddings)]
        # Fail immediately on any rejected batch instead of claiming full success.
        index.upsert(vectors=vectors)
        uploaded += len(batch)
    print(f"Uploaded {uploaded} vectors to {args.index_name}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # API exceptions can include sensitive request details.
        print(f"Filing validation/upload failed ({type(exc).__name__}). No success claimed.")
        raise SystemExit(1)
