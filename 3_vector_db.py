# 3_vector_db.py (FINAL - NEW APPROACH)
# This script uses a fundamentally different, more robust method.
# It processes data in small batches from start to finish, which is
# memory-efficient and guaranteed to avoid the "batch size" error.

import json
import chromadb
from sentence_transformers import SentenceTransformer
import time
import os
import shutil

def create_vector_database_new_approach():
    """
    Creates a ChromaDB vector database using a robust, batch-by-batch
    generation and insertion method to prevent errors.
    """
    print("--- Running the FINAL script with a NEW, more robust approach. ---")
    
    db_path = "chroma_db"
    collection_name = "sec_filings"

    # STEP 1: AGGRESSIVE CLEANUP 
    if os.path.exists(db_path):
        print(f"Found old database at '{db_path}'. Deleting it now.")
        shutil.rmtree(db_path)
        print("Old database deleted.")
        time.sleep(1) # Pause to ensure deletion is processed

    # STEP 2: INITIALIZE DATABASE AND COLLECTION
    print("Initializing a fresh vector database...")
    client = chromadb.PersistentClient(path=db_path)
    embedding_model_name = "all-MiniLM-L6-v2"
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"Collection '{collection_name}' created.")

    # STEP 3: LOAD MODEL AND DATA 
    print("Loading embedding model...")
    model = SentenceTransformer(embedding_model_name)
    print("Embedding model loaded.")

    print("Loading data from 'processed_chunks.json'...")
    try:
        with open("processed_chunks.json", 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        print(f"Successfully loaded {len(chunks_data)} text chunks.")
    except FileNotFoundError:
        print("\nFATAL ERROR: 'processed_chunks.json' not found. Run Step 2 again.")
        return

    # STEP 4: PROCESS AND ADD IN BATCHES
    # Keep model encoding batches small, and also split the chroma add into micro-batches
    batch_size = 500              
    max_add_batch = 4000          
                                  
    total_batches = (len(chunks_data) + batch_size - 1) // batch_size
    print(f"\nStarting to process and add data in {total_batches} batches...")

    for i in range(0, len(chunks_data), batch_size):
        end_index = min(i + batch_size, len(chunks_data))
        current_batch_data = chunks_data[i:end_index]

        documents = [chunk.get('content', '') for chunk in current_batch_data]
        metadatas = [
            {
                'ticker': chunk.get('ticker'),
                'filing_type': chunk.get('filing_type'),
                'source': chunk.get('source')
            } for chunk in current_batch_data
        ]
        
        ids = [str(chunk.get('chunk_id', f"{i+j}")) for j, chunk in enumerate(current_batch_data)]

        
        print(f"  Batch {i // batch_size + 1}/{total_batches}: Generating embeddings for {len(documents)} items...")
        embeddings = model.encode(documents, show_progress_bar=False, convert_to_numpy=True)
        embeddings = embeddings.tolist()  # now a list of lists

        if not (len(embeddings) == len(documents) == len(ids) == len(metadatas)):
            raise ValueError(f"Length mismatch: embeddings={len(embeddings)}, documents={len(documents)}, ids={len(ids)}, metadatas={len(metadatas)}")

        print(f"  Batch {i // batch_size + 1}/{total_batches}: Adding to database in micro-batches (<={max_add_batch})...")
    
        for j in range(0, len(embeddings), max_add_batch):
            j_end = min(j + max_add_batch, len(embeddings))
            emb_sub = embeddings[j:j_end]
            docs_sub = documents[j:j_end]
            meta_sub = metadatas[j:j_end]
            ids_sub = ids[j:j_end]

            print(f"    Adding items {i+j} .. {i+j_end-1} (count={len(ids_sub)}) ...")
            try:
                collection.add(
                    embeddings=emb_sub,
                    documents=docs_sub,
                    metadatas=meta_sub,
                    ids=ids_sub
                )
            except Exception as e:
                print(f"    WARNING: add() failed for micro-batch size {len(ids_sub)}: {e}")
                print("    Retrying micro-batch in tiny sub-chunks of 500...")
                tiny = 500
                for k in range(0, len(emb_sub), tiny):
                    k_end = min(k + tiny, len(emb_sub))
                    collection.add(
                        embeddings=emb_sub[k:k_end],
                        documents=docs_sub[k:k_end],
                        metadatas=meta_sub[k:k_end],
                        ids=ids_sub[k:k_end]
                    )


    print("\n--- SCRIPT COMPLETED SUCCESSFULLY ---")
    print(f"The vector database is fully populated with {collection.count()} items.")
    print("This step is now complete. You can proceed.")

if __name__ == "__main__":
    create_vector_database_new_approach()

# END