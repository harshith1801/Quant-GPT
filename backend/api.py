"""Same-origin FastAPI application; all provider credentials stay on this server."""
import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from .presentation import present_answer, source_url

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
os.environ.setdefault('PINECONE_INDEX_NAME', 'finsight-index-v2')
app = FastAPI(title='Quant GPT', docs_url='/api/docs', openapi_url='/api/openapi.json')
engine = None
engine_lock = threading.Lock()
workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix='analysis')
jobs, jobs_lock = {}, threading.Lock()
NAMES = {'AAPL': 'Apple Inc.', 'MSFT': 'Microsoft Corporation', 'NVDA': 'NVIDIA Corporation'}


def get_engine():
    global engine
    with engine_lock:
        if engine is None:
            try:
                import query_engine
                engine = query_engine
            except (Exception, SystemExit):
                raise HTTPException(503, 'Research services are unavailable. Check server configuration.') from None
    return engine


def valid_ticker(value):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,9}', value):
        raise ValueError('Enter a valid ticker symbol.')
    return value


class AnalysisRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1200)
    tickers: list[str] = Field(min_length=1, max_length=2)

    @field_validator('tickers')
    @classmethod
    def tickers_valid(cls, values):
        values = list(dict.fromkeys(valid_ticker(v) for v in values))
        return values


def company_context(ticker):
    qe = get_engine()
    quote, chart = qe.get_stock_data(ticker)
    news = qe.get_news_and_sentiment(ticker)
    filings, filing_status = [], 'available'
    try:
        filings = qe.get_filing_catalog(qe.PINECONE_INDEX_NAME, ticker)
        if not filings: filing_status = 'empty'
    except Exception:
        filing_status = 'unavailable'
    latest = []
    for form in ('10-Q', '10-K'):
        matches = [f for f in filings if f['filing_type'] == form]
        if matches: latest.append(max(matches, key=lambda f: f['filing_date']))
    points = [{'time': row['Date'].strftime('%Y-%m-%d'), 'value': float(row['Price'])}
              for _, row in chart.iterrows()]
    return {'ticker': ticker, 'name': NAMES.get(ticker, ticker), 'quote': quote,
            'chart': points, 'news': news, 'filings': latest, 'filing_status': filing_status}


@app.get('/api/health')
def health():
    configured = all(os.getenv(k) for k in ('GROQ_API_KEY', 'PINECONE_API_KEY', 'ALPHA_VANTAGE_KEY'))
    return {'status': 'ready' if configured else 'unconfigured'}


@app.get('/api/company/{ticker}')
def context(ticker: str):
    try: return company_context(valid_ticker(ticker))
    except ValueError: raise HTTPException(422, 'Invalid ticker.') from None
    except HTTPException: raise
    except Exception: raise HTTPException(503, 'Company data is temporarily unavailable.') from None


def update(job_id, **values):
    with jobs_lock: jobs[job_id].update(values)


def analyze(job_id, request):
    try:
        qe = get_engine()
        update(job_id, stage='retrieving')
        companies = [company_context(t) for t in request.tickers]
        data, sections, gaps = {}, [], []
        for i, company in enumerate(companies, 1):
            ticker = company['ticker']
            context, _ = qe.get_rag_context(request.question, ticker)
            data.update({f'ticker{i}': ticker, f'stock{i}_quote': company['quote'],
                         f'news{i}': company['news'], f'rag{i}_context': context})
            try:
                evidence = json.loads(context)
                sections.extend(evidence['sections'])
            except (ValueError, KeyError):
                gaps.append(f'No filing evidence was retrieved for {ticker}.')
            sections.extend([
                {'source_id': f'{ticker}:MARKET', 'ticker': ticker, 'kind': 'market',
                 'text': json.dumps(company['quote'], indent=2)},
                {'source_id': f'{ticker}:NEWS', 'ticker': ticker, 'kind': 'news',
                 'text': json.dumps(company['news'], indent=2)},
            ])
        update(job_id, stage='verifying')
        answer = qe.generate_master_insight(request.question,
                    'Single Ticker' if len(companies) == 1 else 'Compare Tickers', data)
        if answer.startswith('Error generating'):
            raise RuntimeError('generation_unavailable')
        presentation = present_answer(answer, sections)
        presentation['notes'].extend(gaps)
        for source in sections: source['url'] = source_url(source)
        update(job_id, stage='complete', result={**presentation, 'question': request.question,
               'companies': companies, 'sources': sections, 'completed_at': time.time()})
    except Exception as error:
        # Never return provider exceptions, payloads, credentials, or stack traces.
        logging.getLogger('quant').warning('Analysis failed: %s', type(error).__name__)
        update(job_id, stage='error', message='Analysis is temporarily unavailable. Your question is preserved; please retry shortly.')


@app.post('/api/analyses', status_code=202)
def start(request: AnalysisRequest):
    with jobs_lock:
        for key in list(jobs):
            if time.time() - jobs[key]['created'] > 3600 and jobs[key]['stage'] in ('complete', 'error'):
                del jobs[key]
        if sum(j['stage'] not in ('complete', 'error') for j in jobs.values()) >= 2:
            raise HTTPException(429, 'Two analyses are already running. Please try again shortly.')
        if len(jobs) >= 64:
            oldest = next((k for k,v in jobs.items() if v['stage'] in ('complete', 'error')), None)
            if oldest: del jobs[oldest]
        job_id = uuid.uuid4().hex
        jobs[job_id] = {'id': job_id, 'stage': 'queued', 'created': time.time()}
    workers.submit(analyze, job_id, request)
    return {'id': job_id, 'stage': 'queued'}


@app.get('/api/analyses/{job_id}')
def progress(job_id: str):
    with jobs_lock:
        if job_id not in jobs: raise HTTPException(404, 'This analysis has expired. Run the question again.')
        return dict(jobs[job_id])


DIST = ROOT / 'frontend' / 'dist'
if (DIST / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')


@app.get('/{path:path}', include_in_schema=False)
def frontend(path: str):
    if path.startswith('api/'): raise HTTPException(404, 'Unknown API route.')
    if path in ('mark.svg',) and (DIST / path).exists(): return FileResponse(DIST / path)
    if not (DIST / 'index.html').exists():
        raise HTTPException(503, 'Frontend not built. Run pnpm build in frontend/.')
    return FileResponse(DIST / 'index.html')
