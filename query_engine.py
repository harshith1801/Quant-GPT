# query_engine.py
# FINAL VERSION - Uses Streamlit's @st.cache_resource for efficient model loading.

import os
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
from dotenv import load_dotenv
import sys
import requests
import pandas as pd
from datetime import datetime
import streamlit as st # <-- THIS IMPORT IS CRITICAL

# --- 1. INITIALIZATION & API KEY LOADING ---

try:
    load_dotenv()
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY") 
    PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")

    if not all([GOOGLE_API_KEY, ALPHA_VANTAGE_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT]):
        print("FATAL ERROR: One or more API keys are missing from your .env file.")
        # We use st.error so the user sees it in the app if it fails
        st.error("FATAL ERROR: One or more API keys are missing from your server's secrets.")
        sys.exit(1)
        
    genai.configure(api_key=GOOGLE_API_KEY)
    
except Exception as e:
    print(f"FATAL ERROR during initialization: {e}")
    st.error(f"FATAL ERROR during initialization: {e}")
    sys.exit(1)

# --- 2. CACHED DATA FETCHER: REAL-TIME STOCKS ---
# (This function is fast and does not need to be changed)
def get_stock_data(ticker):
    """
    Fetches daily historical data from Alpha Vantage and calculates
    the latest quote and chart data from this single source.
    """
    try:
        history_url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&outputsize=compact&apikey={ALPHA_VANTAGE_KEY}'
        r_history = requests.get(history_url)
        r_history.raise_for_status()
        history_data = r_history.json().get('Time Series (Daily)')
        
        if not history_data:
            print(f"Warning: No TIME_SERIES_DAILY data found for {ticker}.")
            return None, pd.DataFrame()

        # 1. Create the Chart Data
        df = pd.DataFrame.from_dict(history_data, orient='index', dtype=float)
        df = df.rename(columns={'4. close': 'Price'})
        df.index = pd.to_datetime(df.index)
        chart_data = df.sort_index(ascending=True)[['Price']]
        chart_data = chart_data.reset_index().rename(columns={'index':'Date'})

        # 2. Calculate the Quote Info (Latest Price, Change)
        if len(chart_data) < 2:
            print(f"Warning: Not enough data to calculate change for {ticker}.")
            return None, chart_data 

        latest_price = chart_data.iloc[-1]['Price']
        previous_price = chart_data.iloc[-2]['Price']
        price_change_raw = latest_price - previous_price
        price_change_percent_raw = (price_change_raw / previous_price)
        change_percent_str = f"{price_change_percent_raw:+.2%}"
        
        quote_info = {
            'price': latest_price,
            'change_percent_str': change_percent_str,
            'change_percent_float': price_change_percent_raw,
            'volume': df.iloc[-1].get('5. volume', 0)
        }
        
        return quote_info, chart_data

    except Exception as e:
        print(f"Error fetching TIME_SERIES_DAILY for {ticker}: {e}")
        return None, pd.DataFrame()

# --- 3. CACHED DATA FETCHER: REAL-TIME NEWS (ALPHA VANTAGE) ---
# (This function is fast and does not need to be changed)
def get_news_and_sentiment(ticker):
    """
    Fetches latest news and sentiment from Alpha Vantage.
    """
    try:
        news_url = (
            f'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&'
            f'tickers={ticker}&'
            f'limit=10&'
            f'apikey={ALPHA_VANTAGE_KEY}'
        )
        r_news = requests.get(news_url)
        r_news.raise_for_status()
        news_data = r_news.json()
        articles = news_data.get('feed', [])
        
        if not articles:
            return {'overall_sentiment_label': 'No recent news found.', 'articles': []}
            
    except Exception as e:
        print(f"Error fetching Alpha Vantage News for {ticker}: {e}")
        return {'overall_sentiment_label': f'Error fetching news: {e}', 'articles': []}

    formatted_articles = []
    overall_sentiment_score = 0
    for article in articles:
        ticker_sentiment_info = next((item for item in article.get('ticker_sentiment', []) if item['ticker'] == ticker), None)
        sentiment_label = "Neutral"
        if ticker_sentiment_info:
            sentiment_label = ticker_sentiment_info.get('ticker_sentiment_label', 'Neutral')
            overall_sentiment_score += float(ticker_sentiment_info.get('ticker_sentiment_score', 0))

        formatted_articles.append({
            'title': article.get('title', 'No Title'),
            'description': article.get('summary', 'No summary available.'),
            'url': article.get('url', '#'),
            'source': article.get('source', 'N/A'),
            'sentiment_label': sentiment_label
        })
        
    if articles:
        avg_score = overall_sentiment_score / len(articles)
        if avg_score > 0.15: overall_sentiment_label = "Positive"
        elif avg_score < -0.15: overall_sentiment_label = "Negative"
        else: overall_sentiment_label = "Neutral"
    else:
        overall_sentiment_label = "No recent news found."

    return {
        'overall_sentiment_label': overall_sentiment_label, 
        'articles': formatted_articles
    }

# --- 4. RAG FETCHER: DEEP DOCUMENT CONTEXT (THIS IS THE FIX) ---

# This function will load our heavy models ONCE and keep them in memory.
@st.cache_resource
def get_query_components():
    """
    Loads and returns the embedding model and Pinecone index.
    This is cached by Streamlit to only run once.
    """
    # This print will now only show in the log ONCE
    print("--- LOADING MODELS (This runs only once) ---")
    try:
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index("finsight-index") 
        
        print("--- MODELS LOADED SUCCESSFULLY ---")
        return embedding_model, index
    except Exception as e:
        print(f"FATAL ERROR: Could not initialize query components: {e}")
        st.error(f"FATAL ERROR: Could not initialize query components: {e}")
        return None, None

def get_rag_context(query, ticker, n_results=4):
    """
    Fetches relevant context chunks from the PINECONE vector database.
    """
    # Get the cached models
    embedding_model, index = get_query_components()
    
    if embedding_model is None or index is None:
        return "Error: Query components failed to load.", []
        
    try:
        query_embedding = embedding_model.encode(query).tolist()
        
        results = index.query(
            vector=query_embedding,
            top_k=n_results,
            filter={"ticker": ticker}, 
            include_metadata=True
        )
        
        if not results['matches']:
             return "No relevant context found in the company's filings for this query.", []

        context_chunks = [match['metadata']['content'] for match in results['matches']]
        sources = [match['metadata'] for match in results['matches']]
        
        return "\n\n---\n\n".join(context_chunks), sources
        
    except Exception as e:
        print(f"Error querying Pinecone for {ticker}: {e}")
        return f"Error retrieving document context: {e}", []

# --- 5. THE MASTER INSIGHT ENGINE (No changes needed) ---

def generate_master_insight(query, analysis_type, data):
    """
    Generates the final, synthesized answer using all available data.
    'data' is a dictionary containing all the fetched information.
    """
    if analysis_type == "Single Ticker":
        ticker1 = data['ticker1']
        prompt = f"""
        You are a world-class Quantitative Financial Analyst. Your name is Quant GPT.
        Your task is to provide a single, synthesized insight to a user's query by integrating three sources of information:
        1.  **Fundamental Data:** Key risks and statements from the company's official 10-K/10-Q filings.
        2.  **Market Data:** Today's live stock price and volume.
        3.  **Sentiment Data:** Today's latest news headlines and their sentiment.
        **CRITICAL RULES:**
        1.  **ANSWER THE QUERY FIRST:** Immediately provide a direct, concise answer to the user's query in the first one or two paragraphs. Do not "beat around the bush."
        2.  **Synthesize, Don't Just List:** You must *connect* the data points. For example, explain *how* the 10-K risk provides context for *today's* news.
        3.  **Be Fact-Based:** Base all answers *only* on the data provided. Do not invent new information.
        4.  **NO FINANCIAL ADVICE:** Never predict prices or tell the user to "buy" or "sell". Just provide objective, data-driven analysis for *them* to make a decision.
        5.  **Answer the Query:** Directly answer the user's specific question.
        6.  **Structure Your Answer:** Provide your answer in three clear parts:
            * **Summary:** A one-paragraph, top-level direct and precise answer to the user's query. Put the concise immediate answer under this section.
            * **Today's Market Snapshot:** A brief and clear summary of today's market and news sentiment.
            * **Connection to Company Filings:** The core analysis, connecting the user's query to the fundamental 10-K data and linking it to the real-time context.
        ---
        **DATA PROVIDED:**
        **1. USER QUERY:** "{query}"
        **2. MARKET DATA ({ticker1}):**
        * Latest Price: ${data['stock1_quote']['price']:.2f}
        * Today's Change: {data['stock1_quote']['change_percent_str']}
        * Today's Volume: {data['stock1_quote']['volume']:,}
        **3. SENTIMENT DATA ({ticker1}):**
        * Overall Sentiment: "{data['news1']['overall_sentiment_label']}"
        * Key Headlines: {[(a['title'], a['sentiment_label']) for a in data['news1']['articles']]}
        **4. FUNDAMENTAL DATA ({ticker1} from 10-K/10-Q Filings):**
        {data['rag1_context']}
        ---
        Begin your analysis.
        """
    else: # Comparative Analysis
        ticker1 = data['ticker1']
        ticker2 = data['ticker2']
        prompt = f"""
        You are a world-class Quantitative Financial Analyst. Your name is Quant GPT.
        Your task is to provide a **comparative analysis** for a user's query. You must synthesize and contrast three data sources for *both* companies.
        **CRITICAL RULES:**
        1.  **ANSWER THE QUERY FIRST:** Immediately provide a direct, concise answer comparing the two companies based on the user's query.
        2.  **Compare & Contrast:** Your primary goal is to identify similarities and differences.
        3.  **Be Fact-Based:** Base all answers *only* on the data provided.
        4.  **NO FINANCIAL ADVICE:** Never predict prices or tell the user to "buy" or "sell".
        5.  **Answer the Query:** Directly answer the user's comparative question.
        6.  **Structure Your Answer:**
            * **Summary:** A one-paragraph, top-level answer comparing the two.
            * **Today's Market Snapshot:** A brief comparison of today's market and news sentiment.
            * **Connection to Company Filings:** The core comparison, connecting the user's query to the fundamental 10-K data for both companies.
        ---
        **DATA PROVIDED:**
        **1. USER QUERY:** "{query}"
        **2. DATA FOR {ticker1}:**
        * **Market Data:** Price: ${data['stock1_quote']['price']:.2f}, Change: {data['stock1_quote']['change_percent_str']}, Volume: {data['stock1_quote']['volume']:,}
        * **Sentiment Data:** Overall: "{data['news1']['overall_sentiment_label']}"
        * **Fundamental Data (from 10-K/10-Q):** {data['rag1_context']}
        **3. DATA FOR {ticker2}:**
        * **Market Data:** Price: ${data['stock2_quote']['price']:.2f}, Change: {data['stock2_quote']['change_percent_str']}, Volume: {data['stock2_quote']['volume']:,}
        * **Sentiment Data:** Overall: "{data['news2']['overall_sentiment_label']}"
        * **Fundamental Data (from 10-K/10-Q):** {data['rag2_context']}
        ---
        Begin your comparative analysis.
        """

    # Generate the insight
    try:
        model = genai.GenerativeModel('models/gemini-pro-latest')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error in master insight generation: {e}")
        return f"Error generating AI insight: {e}"

