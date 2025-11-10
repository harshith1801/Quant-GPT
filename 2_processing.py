# 2_processing.py
# # This script parses the raw HTML filings, extracts clean text, and splits it into smaller chunks, saving them to a JSON file.

import os
import json
from bs4 import BeautifulSoup
from langchain.text_splitter import RecursiveCharacterTextSplitter
import re
import html

def get_ticker_from_path(file_path):
    """Extracts the ticker (e.g., 'AAPL') from the file path."""
    try:
        parts = file_path.split(os.sep)
        if "sec-edgar-filings" in parts:
            idx = parts.index("sec-edgar-filings")
            return parts[idx + 1] 
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"

def get_filing_type_from_path(file_path):
    """Extracts the filing type (e.g., '10-K') from the file path."""
    try:
        parts = file_path.split(os.sep)
        if "sec-edgar-filings" in parts:
            idx = parts.index("sec-edgar-filings")
            return parts[idx + 2] 
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"

def chunk_filing(filing_path):
    """
    Reads a single filing, intelligently extracts clean text,
    and returns a list of chunk dictionaries.
    """
    print(f"--- Processing: {filing_path}")
    try:
        with open(filing_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"    Error reading file: {e}")
        return []

    if not content:
        print(f"    Warning: Empty file.")
        return []

    try:
        cleaned_content = html.unescape(content)
        
        soup = BeautifulSoup(cleaned_content, 'html.parser')

        for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]):
            script_or_style.decompose()
        
        # Find all text within these common readable tags
        text_elements = soup.find_all(['p', 'div', 'span', 'table', 'th', 'tr', 'td', 'h1', 'h2', 'h3', 'h4', 'li'])
        
        clean_text = ""
        if text_elements:
            clean_text = " ".join([elem.get_text(strip=True) for elem in text_elements])
        
        if not clean_text or len(clean_text) < 200:
            # Fallback: get all text from the body
            print("    Warning: Tag-based extraction failed, using body text fallback.")
            if soup.body:
                clean_text = soup.body.get_text(strip=True, separator=" ")
            else:
                clean_text = soup.get_text(strip=True, separator=" ")
        
        # Final cleanup of leftover whitespace and non-ASCII
        clean_text = re.sub(r'\s+', ' ', clean_text) # Consolidate whitespace
        clean_text = re.sub(r'[^\x00-\x7F]+', ' ', clean_text) # Remove non-ASCII
            
    except Exception as e:
        print(f"    Error parsing HTML with BeautifulSoup: {e}")
        clean_text = "" 

    if len(clean_text) < 100:
        print(f"    Warning: Very little clean text extracted (<100 chars). Skipping.")
        return []


    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=300,
        length_function=len
    )
    
    chunks = text_splitter.split_text(clean_text)
    
    ticker = get_ticker_from_path(filing_path)
    filing_type = get_filing_type_from_path(filing_path)
    source_path = os.path.relpath(filing_path, 'sec_filings') 
    
    chunks_with_metadata = []
    for i, chunk in enumerate(chunks):
        chunks_with_metadata.append({
            'chunk_id': f'{ticker}_{filing_type}_{i}', 
            'content': chunk,
            'ticker': ticker,
            'filing_type': filing_type,
            'source': source_path
        })
        
    return chunks_with_metadata

def process_all_filings(root_dir='sec_filings'):
    """
    Walks through all downloaded filings and processes them.
    """
    all_chunks = []
    filings_root = os.path.join(root_dir, 'sec-edgar-filings')
    
    if not os.path.exists(filings_root):
        print(f"Error: Directory not found: {filings_root}")
        print("Did you run the 1_data_collection.py script?")
        return

    print("Starting processing... This may take a moment.")
    for dirpath, dirnames, filenames in os.walk(filings_root):
        for filename in filenames:
            # Process the full submission text file
            if filename == 'full-submission.txt':
                file_path = os.path.join(dirpath, filename)
                chunks_data = chunk_filing(file_path)
                if chunks_data:
                    all_chunks.extend(chunks_data)

    if not all_chunks:
        print("CRITICAL: No chunks were processed. Something is wrong.")
        return

    # Save to a new JSON file
    output_file = 'processed_chunks_CLEAN.json'
    print(f"\nSaving {len(all_chunks)} clean chunks to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
        
    print(f"Processing complete. Clean data is in '{output_file}'.")

if __name__ == "__main__":
    process_all_filings()

# END