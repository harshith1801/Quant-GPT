# app.py
# FINAL VERSION - Uses Alpha Vantage for News, fixes chart bug, and formats sources.

import streamlit as st
import pandas as pd
import altair as alt
import sys

# Ensure the app can find the query_engine
sys.path.append('.') 
try:
    # We import all functions from your 'query_engine.py' file
    from query_engine import (
        get_stock_data, 
        get_news_and_sentiment, 
        get_rag_context, 
        generate_master_insight
    )
except ImportError:
    st.error("Error: Could not find 'query_engine.py'. Make sure '4_query_engine.py' is renamed to 'query_engine.py'.")
    st.stop()
except Exception as e:
    st.error(f"An unexpected error occurred on startup: {e}")
    st.stop()

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Quant GPT - Quantitative Analyst",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CACHED DATA FUNCTIONS ---
def cached_get_stock_data(ticker):
    """Cached function to get stock data."""
    return get_stock_data(ticker)

def cached_get_news_and_sentiment(ticker):
    """Cached function to get news and sentiment."""
    return get_news_and_sentiment(ticker)

@st.cache_data(show_spinner="Searching deep document archives...")
def cached_get_rag_context(query, ticker):
    """Cached function to get RAG context."""
    return get_rag_context(query, ticker)


# --- 3. SIDEBAR (CONTROLS) ---
with st.sidebar:
    st.title("📈 Quant GPT")
    st.markdown("Your AI-Powered Quantitative Analyst")
    st.divider()
    
    available_tickers = ["AAPL", "MSFT", "NVDA"]
    analysis_type = st.radio(
        "Select Analysis Type:",
        ["Single Ticker", "Compare Tickers"],
        horizontal=True,
        key="analysis_type"
    )
    
    st.subheader("Select Tickers")
    if analysis_type == "Single Ticker":
        ticker1 = st.selectbox("Select Company:", available_tickers, key="ticker1")
        ticker2 = None
    else:
        col1, col2 = st.columns(2)
        with col1:
            ticker1 = st.selectbox("Company A:", available_tickers, key="ticker1_comp", index=0)
        with col2:
            ticker2_options = [t for t in available_tickers if t != ticker1]
            ticker2 = st.selectbox("Company B:", ticker2_options, key="ticker2_comp", index=1 if len(ticker2_options) > 1 else 0)

    st.divider()
    
    st.subheader("Enter Your Query")
    query_text = st.text_area(
        "Ask a question based on market data, news, and 10-K filings:",
        placeholder="e.g., What are the main risks for this company and how do they relate to available news?",
        height=150,
        key="query"
    )

    submit_button = st.button("Analyze", type="primary", use_container_width=True)
    
    st.markdown("---")
    st.caption("Built by Harshith Chejerla | Powered by Groq and Alpha Vantage.")

# --- 4. MAIN PAGE (DISPLAY) ---
st.header(f"Analysis: {ticker1}{' vs. ' + ticker2 if analysis_type == 'Compare Tickers' and ticker2 else ''}")
st.markdown("Ask a question in the sidebar to begin your analysis.")

if submit_button:
    if not query_text:
        st.warning("Please enter a query in the sidebar to begin analysis.")
    else:
        # --- Data Fetching ---
        with st.spinner("Fetching daily closes, news and filing evidence... Please wait."):
            
            stock1_quote, stock1_chart_data = cached_get_stock_data(ticker1)
            news1 = cached_get_news_and_sentiment(ticker1)
            rag1_context, rag1_sources = cached_get_rag_context(query_text, ticker1)
            
            data_payload = {
                "ticker1": ticker1, "stock1_quote": stock1_quote,
                "news1": news1, "rag1_context": rag1_context, "ticker2": None,
            }

            if analysis_type == "Compare Tickers" and ticker2:
                stock2_quote, stock2_chart_data = cached_get_stock_data(ticker2)
                news2 = cached_get_news_and_sentiment(ticker2)
                rag2_context, rag2_sources = cached_get_rag_context(query_text, ticker2)
                
                data_payload.update({
                    "ticker2": ticker2, "stock2_quote": stock2_quote,
                    "news2": news2, "rag2_context": rag2_context,
                })

        # --- Generate the Master Insight ---
        with st.spinner("🤖 AI is synthesizing insights..."):
            try:
                # Check for failed data fetches
                # Preserve explicit unavailable status; never invent a zero-dollar quote.
                if not (stock1_quote or {}).get('available', False):
                    st.error(f"Daily-close data unavailable: {(stock1_quote or {}).get('status', 'api_error')}")
                if ticker2 and not (data_payload.get('stock2_quote') or {}).get('available', False):
                    st.error(f"Daily-close data unavailable for {ticker2}.")

                master_insight = generate_master_insight(query_text, analysis_type, data_payload)
            except Exception as e:
                st.error(f"Error during AI insight generation: {e}")
                master_insight = None

        # --- Display the Results ---
        if master_insight:
            col1, col2 = st.columns([0.6, 0.4]) # Main layout
            
            with col1:
                st.header("🤖 Quant GPT Analysis")
                st.markdown(master_insight) # Display AI answer
                st.divider()

                # --- NEW NEWS DISPLAY ---
                # This section is updated to read the Alpha Vantage format
                st.subheader(f"News & Sentiment: {ticker1}")
                st.markdown(f"**Overall Sentiment:** *{news1.get('overall_sentiment_label', 'N/A')}*")
                for article in news1.get('articles', []):
                    with st.expander(f"**{article.get('sentiment_label', 'N/A')}** | {article.get('title', 'No Title')}"):
                        st.write(article.get('description', 'No summary available.'))
                        # This displays the clickable "Read More" link
                        st.write(f"[Read More]({article.get('url', '#')}) (Source: {article.get('source', 'N/A')})")
                
                if analysis_type == "Compare Tickers" and ticker2:
                    st.divider()
                    st.subheader(f"News & Sentiment: {ticker2}")
                    st.markdown(f"**Overall Sentiment:** *{news2.get('overall_sentiment_label', 'N/A')}*")
                    for article in news2.get('articles', []):
                        with st.expander(f"**{article.get('sentiment_label', 'N/A')}** | {article.get('title', 'No Title')}"):
                            st.write(article.get('description', 'No summary available.'))
                            st.write(f"[Read More]({article.get('url', '#')}) (Source: {article.get('source', 'N/A')})")

                st.divider()
                # --- FINAL SOURCES FIX ---
                # This section now displays the sources as clean, clickable links.
                with st.expander("Show Fundamental 10-K/10-Q Sources Used"):
                    st.subheader(f"Source Documents ({ticker1})")
                    if rag1_sources:
                        for i, source in enumerate(rag1_sources):
                            try:
                                # Parse the source path to get the filing's unique ID
                                parts = source.get('source', '').split('/')
                                accession_number = parts[-2] # The '0000320193-20-000096' part
                                accession_no_dashes = accession_number.replace('-', '')
                                cik = accession_number.split('-')[0].lstrip('0') # The '320193' part
                                
                                # Build the public SEC URL
                                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{accession_number}-index.htm"
                                
                                # Display in a clean, linked format
                                st.markdown(f"**Source {i+1}: {source.get('ticker')} {source.get('filing_type')}**")
                                st.markdown(f"[View Full SEC Filing at SEC.gov]({url})")
                            except Exception as e:
                                # Fallback if parsing fails for any reason
                                st.markdown(f"**Source {i+1}:** {source.get('source')}")
                    else:
                        st.write("No source documents found.")
                    
                    if analysis_type == "Compare Tickers" and ticker2:
                        st.divider()
                        st.subheader(f"Source Documents ({ticker2})")
                        if rag2_sources:
                            for i, source in enumerate(rag2_sources):
                                try:
                                    parts = source.get('source', '').split('/')
                                    accession_number = parts[-2]
                                    accession_no_dashes = accession_number.replace('-', '')
                                    cik = accession_number.split('-')[0].lstrip('0')
                                    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{accession_number}-index.htm"
                                    
                                    st.markdown(f"**Source {i+1}: {source.get('ticker')} {source.get('filing_type')}**")
                                    st.markdown(f"[View Full SEC Filing at SEC.gov]({url})")
                                except Exception as e:
                                    st.markdown(f"**Source {i+1}:** {source.get('source')}")
                        else:
                            st.write("No source documents found.")

            with col2:
                st.header(f"📊 Market Data: {ticker1}")
                if stock1_quote and stock1_quote.get('available', False):
                    metric_col1, metric_col2 = st.columns(2)
                    metric_col1.metric(f"Daily close ({stock1_quote['date']})", f"${stock1_quote['price']:.2f}")
                    metric_col2.metric("Change", stock1_quote.get('change_percent_str', 'N/A'), 
                                      delta=stock1_quote.get('change_percent_str'))
                else:
                    st.error(f"Could not load daily-close data for {ticker1}.")

                if not stock1_chart_data.empty:
                    # --- FINAL CHART FIX ---
                    # This is the new, correct chart code that will not crash.
                    
                    # Base chart
                    base = alt.Chart(stock1_chart_data).encode(
                        x=alt.X('Date', title='Date'),
                        tooltip=[
                            alt.Tooltip('Date', format='%Y-%m-%d'),
                            alt.Tooltip('Price', format='$.2f')
                        ]
                    )
                    
                    # Line layer
                    line = base.mark_line(
                        color='#0068C9' # A nice blue
                    ).encode(
                        y=alt.Y('Price', title='Price (USD)', scale=alt.Scale(zero=False))
                    )
                    
                    # Create a "nearest" selection tool
                    nearest = alt.selection_point(name='nearest', nearest=True, on='mouseover',
                                                fields=['Date'], empty=False)
                    
                    # Points layer for hover interactivity
                    points = line.mark_point().encode(
                        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
                    ).add_params(
                        nearest
                    )
                    
                    # Create a rule to follow the mouse
                    rule = base.mark_rule(color='gray').encode(
                        x='Date',
                    ).transform_filter(
                        nearest
                    )
                    
                    # Layer all charts: line + points + rule
                    chart = alt.layer(line, points, rule).interactive()
                    
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.warning(f"Could not load historical chart data for {ticker1}.") 
                
                if analysis_type == "Compare Tickers" and ticker2:
                    st.divider()
                    st.header(f"📊 Market Data: {ticker2}")
                    if stock2_quote and stock2_quote.get('available', False):
                        metric_col3, metric_col4 = st.columns(2)
                        metric_col3.metric(f"Daily close ({stock2_quote['date']})", f"${stock2_quote['price']:.2f}")
                        metric_col4.metric("Change", stock2_quote.get('change_percent_str', 'N/A'),
                                          delta=stock2_quote.get('change_percent_str'))
                    else:
                        st.error(f"Could not load daily-close data for {ticker2}.")

                    if not stock2_chart_data.empty:
                        # --- FINAL CHART FIX (for Ticker 2) ---
                        base2 = alt.Chart(stock2_chart_data).encode(
                            x=alt.X('Date', title='Date'),
                            tooltip=[
                                alt.Tooltip('Date', format='%Y-%m-%d'),
                                alt.Tooltip('Price', format='$.2f')
                            ]
                        )
                        line2 = base2.mark_line(color='#00A86B').encode( # Green
                            y=alt.Y('Price', title='Price (USD)', scale=alt.Scale(zero=False))
                        )
                        nearest2 = alt.selection_point(name='nearest2', nearest=True, on='mouseover', fields=['Date'], empty=False)
                        points2 = line2.mark_point().encode(
                            opacity=alt.condition(nearest2, alt.value(1), alt.value(0))
                        ).add_params(
                            nearest2
                        )
                        rule2 = base2.mark_rule(color='gray').encode(x='Date').transform_filter(nearest2)
                        
                        chart2 = alt.layer(line2, points2, rule2).interactive()
                        
                        st.altair_chart(chart2, use_container_width=True)
                    else:
                        st.warning(f"Could not load historical chart data for {ticker2}.")

