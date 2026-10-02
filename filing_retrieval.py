"""Metadata-aware filing retrieval; never changes the vector database."""
import math
import re
from datetime import date


def latest_form(query):
    """Only constrain explicit recent-period requests, not historical comparisons."""
    text = query.lower()
    if re.search(r'\b(?:19|20)\d{2}\b|\b(historical|history|compare|comparison)\b', text):
        return None
    if not re.search(r'\b(latest|recent|current|newest|last)\b', text):
        return None
    if re.search(r'\b(quarter|quarterly|10-q)\b', text):
        return '10-Q'
    if re.search(r'\b(annual|annually|year|yearly|10-k)\b', text):
        return '10-K'
    return None


def filing_catalog(index, ticker):
    """Read all ticker metadata, not a similarity sample that can miss filings.

    The ingestion pipeline prefixes every vector ID with TICKER_. Dates and
    accessions come from metadata, never from parsing IDs or company constants.
    """
    filings = {}
    for ids in index.list(prefix=f'{ticker}_', limit=100):
        vector_ids = [item if isinstance(item, str) else item.id for item in ids]
        for vector in index.fetch(ids=vector_ids)['vectors'].values():
            m = vector['metadata']
            if m.get('ticker') != ticker:
                continue
            try:
                date.fromisoformat(m.get('filing_date', ''))
            except ValueError:
                continue
            key = (m.get('filing_type'), m['filing_date'], m.get('accession_number', ''))
            filings[key] = dict(zip(('filing_type', 'filing_date', 'accession_number'), key))
    return list(filings.values())


def retrieve(query, ticker, model, index, catalog, n_results=4):
    form = latest_form(query)
    filters = {'ticker': ticker}
    selection = 'Semantic retrieval with a small recency preference; evidence may be historical.'
    if form:
        filings = [f for f in catalog if f['filing_type'] == form]
        if not filings:
            return [], f'No dated {form} is available. The requested latest filing cannot be verified.'
        newest = max(filings, key=lambda f: (f['filing_date'], f['accession_number']))
        filters.update(filing_type=form, filing_date=newest['filing_date'])
        if newest['accession_number']:
            filters['accession_number'] = newest['accession_number']
        selection = f"Newest available {form} in this index: filed {newest['filing_date']}, accession {newest['accession_number']}. This is not a guarantee of SEC-wide freshness."

    # Financial and risk terminology describes the evidence we need, rather than
    # letting generic words like 'filing' favor cover pages and accounting policies.
    search = query
    if form and re.search(r'performance|results|financial', query, re.I):
        search = 'Financial results: net sales revenue, net income, earnings per share, year-over-year growth, products and services performance.'
    if re.search(r'\brisks?\b', query, re.I):
        search += ' Risk factors competition supply chain regulatory trade tariffs business materially adversely affect.'
    matches = index.query(vector=model.encode(search).tolist(), top_k=max(24, n_results),
                          filter=filters, include_metadata=True)['matches']
    historical = bool(re.search(r'\b(?:19|20)\d{2}\b|\bhistor', query, re.I))

    def rank(match):
        bonus = 0.0
        if not form and not historical:
            try:
                age = max(0, (date.today() - date.fromisoformat(match['metadata']['filing_date'])).days)
                # At most 0.04 cosine points: recency cannot rescue weak relevance.
                bonus = 0.04 * math.exp(-age / 730)
            except (KeyError, ValueError):
                pass
        return float(match['score']) + bonus

    ranked = sorted(matches, key=rank, reverse=True)
    return [dict(m['metadata'], chunk_id=m['id']) for m in ranked[:n_results]], selection
