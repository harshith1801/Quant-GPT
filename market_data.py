"""Alpha Vantage daily closes and explicit news availability, with shared caching."""
from datetime import datetime, timezone
import math
import threading
import time

import pandas as pd
import requests
import streamlit as st


def now():
    return datetime.now(timezone.utc).isoformat()


def api_status(payload):
    """HTTP 200 can still contain an API failure instead of data."""
    for field in ('Error Message', 'Note', 'Information'):
        if field in payload:
            message = str(payload[field])
            lower = message.lower()
            limited = any(word in lower for word in ('rate limit', 'call frequency', 'requests per', 'api limit', 'api calls per'))
            return ('rate_limited' if limited else 'api_error'), message
    return 'ok', ''


@st.cache_resource
def request_gate():
    return threading.Lock(), {'last_request': 0.0}


def fetch(function, ticker, api_key):
    params = {'function': function, 'apikey': api_key}
    params.update({'symbol': ticker, 'outputsize': 'compact'} if function == 'TIME_SERIES_DAILY'
                  else {'tickers': ticker, 'limit': 10, 'sort': 'LATEST'})
    lock, state = request_gate()
    try:
        # Serialize only real requests; cached reruns do not wait or spend quota.
        with lock:
            time.sleep(max(0, 1.1 - (time.monotonic() - state['last_request'])))
            state['last_request'] = time.monotonic()
            response = requests.get('https://www.alphavantage.co/query', params=params, timeout=30)
        if response.status_code == 429:
            return {}, 'rate_limited', 'Alpha Vantage HTTP 429: rate limited.', now()
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return {}, 'api_error', 'Invalid Alpha Vantage response.', now()
        status, message = api_status(payload)
        return payload, status, message.replace(api_key, '[REDACTED]') if api_key else message, now()
    except (requests.RequestException, ValueError):
        # Request exceptions can contain the credential-bearing URL: never expose it.
        return {}, 'api_error', 'Alpha Vantage request failed or returned invalid data.', now()


def parse_stock(payload, status='ok', message='', fetched_at=None):
    failed = {'available': False, 'status': status, 'message': message,
              'date': None, 'fetched_at': fetched_at, 'data_kind': 'daily_close'}
    if status != 'ok':
        return failed, pd.DataFrame()
    history = payload.get('Time Series (Daily)')
    if not history:
        return dict(failed, status='no_data', message='No daily price records returned.'), pd.DataFrame()
    try:
        df = pd.DataFrame.from_dict(history, orient='index', dtype=float)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        latest = df.iloc[-1]
        price, volume = float(latest['4. close']), float(latest['5. volume'])
        if not math.isfinite(price) or not math.isfinite(volume) or price <= 0 or volume < 0:
            raise ValueError('Invalid latest record')
        previous = float(df.iloc[-2]['4. close']) if len(df) > 1 else None
        change = (price / previous - 1) if previous and math.isfinite(previous) else None
        quote = dict(available=True, status='ok', message='', date=df.index[-1].strftime('%Y-%m-%d'),
                     fetched_at=fetched_at, data_kind='daily_close', price=price, volume=int(volume),
                     previous_date=df.index[-2].strftime('%Y-%m-%d') if len(df) > 1 else None,
                     change_percent_float=change,
                     change_percent_str=f'{change:+.2%}' if change is not None else 'N/A')
        chart = df[['4. close']].rename(columns={'4. close': 'Price'}).rename_axis('Date').reset_index()
        return quote, chart
    except (ValueError, KeyError, TypeError, IndexError):
        return dict(failed, status='api_error', message='Invalid daily price records.'), pd.DataFrame()


def parse_news(payload, ticker, status='ok', message='', fetched_at=None):
    result = dict(available=False, status=status, message=message, fetched_at=fetched_at,
                  overall_sentiment_label='Unavailable', articles=[])
    if status != 'ok':
        result['overall_sentiment_label'] = ('Unavailable (rate limited)' if status == 'rate_limited'
                                             else 'Unavailable (API error)')
        return result
    feed = payload.get('feed')
    if not isinstance(feed, list):
        return dict(result, status='api_error', message='Alpha Vantage did not return a news feed.',
                    overall_sentiment_label='Unavailable (API error)')
    if not feed:
        return dict(result, status='no_news', available=True,
                    message='News request succeeded but returned no articles.',
                    overall_sentiment_label='No articles returned; sentiment unavailable')
    articles, scores = [], []
    for article in feed[:10]:
        if not isinstance(article, dict):
            continue
        sentiment = next((s for s in article.get('ticker_sentiment', []) if s.get('ticker') == ticker), {})
        try:
            score = float(sentiment['ticker_sentiment_score'])
            if math.isfinite(score):
                scores.append(score)
        except (KeyError, TypeError, ValueError):
            pass
        articles.append(dict(title=article.get('title', 'Untitled'), description=article.get('summary', ''),
                             url=article.get('url', ''), source=article.get('source', ''),
                             published_at=article.get('time_published'),
                             sentiment_label=sentiment.get('ticker_sentiment_label', 'Unavailable')))
    label = 'Unavailable (no ticker sentiment scores)'
    if scores:
        average = sum(scores) / len(scores)
        label = 'Positive' if average > .15 else 'Negative' if average < -.15 else 'Neutral'
    return dict(result, available=True, status='ok', overall_sentiment_label=label, articles=articles)


@st.cache_data(ttl=21600, show_spinner=False, max_entries=128)
def cached_stock(ticker, api_key):
    """Daily closes reused for six hours, including failure status."""
    return parse_stock(*fetch('TIME_SERIES_DAILY', ticker, api_key))


@st.cache_data(ttl=7200, show_spinner=False, max_entries=128)
def cached_news(ticker, api_key):
    """News/status reused for two hours, rather than retrying on every rerun."""
    payload, status, message, fetched_at = fetch('NEWS_SENTIMENT', ticker, api_key)
    return parse_news(payload, ticker, status, message, fetched_at)
