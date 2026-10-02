# query_engine.py
# FINAL VERSION - Uses Streamlit's @st.cache_resource for efficient model loading.

import os
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from groq import Groq
from filing_retrieval import filing_catalog, retrieve
from answer_grounding import format_evidence, generate_grounded_answer, complete_balance_evidence
from dotenv import load_dotenv
import sys
import streamlit as st # <-- THIS IMPORT IS CRITICAL

# --- 1. INITIALIZATION & API KEY LOADING ---

try:
    load_dotenv()
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY") 
    PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "finsight-index")

    if not all([GROQ_API_KEY, ALPHA_VANTAGE_KEY, PINECONE_API_KEY]):
        print("FATAL ERROR: One or more API keys are missing from your .env file.")
        # We use st.error so the user sees it in the app if it fails
        st.error("FATAL ERROR: One or more API keys are missing from your server's secrets.")
        sys.exit(1)
        
    groq_client = Groq(api_key=GROQ_API_KEY, timeout=60.0)
    
except Exception as e:
    print(f"FATAL ERROR during initialization: {type(e).__name__}")
    st.error(f"FATAL ERROR during initialization: {type(e).__name__}")
    sys.exit(1)

# --- 2. ALPHA VANTAGE MARKET DATA AND NEWS ---
from market_data import cached_stock, cached_news


def get_stock_data(ticker):
    return cached_stock(ticker.strip().upper(), ALPHA_VANTAGE_KEY)


def get_news_and_sentiment(ticker):
    return cached_news(ticker.strip().upper(), ALPHA_VANTAGE_KEY)


# --- 4. RAG FETCHER: DEEP DOCUMENT CONTEXT (THIS IS THE FIX) ---

# This function will load our heavy models ONCE and keep them in memory.
@st.cache_resource
def get_query_components(index_name):
    """
    Loads and returns the embedding model and Pinecone index.
    This is cached by Streamlit to only run once.
    """
    # This print will now only show in the log ONCE
    print("--- LOADING MODELS (This runs only once) ---")
    try:
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(index_name)
        
        print("--- MODELS LOADED SUCCESSFULLY ---")
        return embedding_model, index
    except Exception as e:
        print(f"FATAL ERROR: Could not initialize query components: {e}")
        st.error(f"FATAL ERROR: Could not initialize query components: {e}")
        return None, None

@st.cache_data(ttl=900, show_spinner=False)
def get_filing_catalog(index_name, ticker):
    _, index = get_query_components(index_name)
    return filing_catalog(index, ticker)

def get_rag_context(query, ticker, n_results=4):
    """
    Fetches relevant context chunks from the PINECONE vector database.
    """
    # Get the cached models
    embedding_model, index = get_query_components(PINECONE_INDEX_NAME)
    
    if embedding_model is None or index is None:
        return "Error: Query components failed to load.", []
        
    try:
        ticker = ticker.upper()
        sources, selection = retrieve(
            query, ticker, embedding_model, index,
            get_filing_catalog(PINECONE_INDEX_NAME, ticker), n_results,
        )
        if not sources:
            return selection + " No relevant filing evidence retrieved.", []

        sources = complete_balance_evidence(query, sources, index)
        return format_evidence(sources, selection), sources

    except Exception as e:
        print(f"Error querying Pinecone for {ticker}: {e}")
        return f"Error retrieving document context: {e}", []

# --- 5. GROUNDED ANSWER GENERATION ---

def generate_master_insight(query, analysis_type, data):
    """Generate and review cited claims before displaying financial answers."""
    try:
        return generate_grounded_answer(groq_client, query, data, analysis_type)
    except Exception as e:
        # Never expose request payloads or API credentials in errors.
        error_type = type(e).__name__
        status = getattr(e, "status_code", None)
        detail = f"{error_type}, HTTP {status}" if isinstance(status, int) else error_type
        print(f"Error in grounded insight generation: {detail}")
        return f"Error generating verified AI insight: {detail}"
