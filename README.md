# Quant-GPT: Your AI-Powered Quantitative Analyst

Quant-GPT is an AI-powered quantitative analyst that solves information overload by combining 3 critical data streams in real-time. It synthesizes **deep fundamental data** from SEC filings, **live market data** from Alpha Vantage, and **real-time news sentiment** to provide a single, data-driven answer to complex financial questions. Instead of spending hours on manual research, users can ask a natural language question and receive an instant, synthesized insight.

This project is a full-stack, end-to-end **RAG (Retrieval-Augmented Generation)** pipeline. A Python script processes and embeds SEC filings into a **Pinecone** cloud vector database. When a user asks a question, the backend retrieves relevant context from Pinecone, fetches live market and news APIs, and then synthesizes all three data streams in a master prompt for the LLM. The entire application is built with `Python` and `Streamlit` and is deployed live on **Hugging Face Spaces**.

Experience the AI analyst in action. You can interact with Quant GPT here: https://huggingface.co/spaces/harshith23/Quant-GPT 
