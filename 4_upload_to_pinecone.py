# 4_upload_to_pinecone.py
# This one-time script uploads all processed text chunks and their embeddings to the Pinecone cloud database.

import os
import json
import pandas as pd
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from tqdm import tqdm

# STEP 1: INITIALIZATION
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
INDEX_NAME = "finsight-index" 

if not PINECONE_API_KEY or not PINECONE_ENVIRONMENT:
    print("Error: Pinecone API key or environment not found in .env file.")
    exit()

# Load the same embedding model
print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")
print("Model loaded.")

# Load the clean data
print("Loading processed chunks...")
try:
    with open('processed_chunks_CLEAN.json', 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)
    print(f"Loaded {len(chunks_data)} chunks.")
except FileNotFoundError:
    print("Error: 'processed_chunks_CLEAN.json' not found.")
    print("Please run the 2_processing.py script first.")
    exit()
except Exception as e:
    print(f"Error loading JSON: {e}")
    exit()

# STEP 2: CONNECT TO PINECONE
try:
    print("Connecting to Pinecone...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    if INDEX_NAME not in pc.list_indexes().names():
        print(f"Index '{INDEX_NAME}' not found. Creating it...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=384, 
            metric='cosine',
            spec=ServerlessSpec(
                cloud='aws', 
                region='us-east-1' 
            )
        )
        print("Index created. Please wait a moment for it to initialize...")
    
    # Get the index
    index = pc.Index(INDEX_NAME)
    print("Connected to index.")
    print(index.describe_index_stats())

except Exception as e:
    print(f"Error connecting to Pinecone: {e}")
    exit()

# STEP 3: EMBED AND UPLOAD IN BATCHES
batch_size = 100 
print(f"Starting upload in batches of {batch_size}...")

for i in tqdm(range(0, len(chunks_data), batch_size)):
    # Get the batch of data
    batch = chunks_data[i : i + batch_size]
    
    texts = [chunk['content'] for chunk in batch]
    
    # Create unique IDs for this batch
    ids = [chunk['chunk_id'] for chunk in batch]
    
    # Create embeddings
    embeddings = model.encode(texts).tolist()
    
    # Create metadata to store alongside vectors
    metadata = []
    for chunk in batch:
        metadata.append({
            'ticker': chunk['ticker'],
            'filing_type': chunk['filing_type'],
            'source': chunk['source'],
            'content': chunk['content'] 
        })
    
    vectors_to_upload = list(zip(ids, embeddings, metadata))
    
    try:
        index.upsert(vectors=vectors_to_upload)
    except Exception as e:
        print(f"Error uploading batch {i}: {e}")

print("\n UPLOAD COMPLETE")
print(f"All {len(chunks_data)} vectors have been uploaded to Pinecone.")
print(index.describe_index_stats())

# END