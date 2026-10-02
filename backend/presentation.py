"""Lossless presentation of verified answers; no extra model-generated facts."""
import re


def present_answer(answer, sections):
    known = {s['source_id']: s for s in sections}
    claims, notes = [], []
    for paragraph in answer.split('\n\n'):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        match = re.search(r'\(([^()]*)\)\s*$', paragraph)
        ids = re.findall(r'\b[A-Z][A-Z0-9.\-]*:(?:F\d+|MARKET|NEWS)\b', match[1]) if match else []
        ids = [i for i in ids if i in known]
        if paragraph.startswith('- ') and ids:
            text = paragraph[2:match.start()].strip()
            kind = 'risk' if re.search(r'\brisk|adverse|constraints|uncertaint|tariff', text, re.I) else 'financial'
            if any(i.endswith(':NEWS') for i in ids): kind = 'news'
            if any(i.endswith(':MARKET') for i in ids): kind = 'market'
            if text.startswith('Interpretation'): kind = 'interpretation'
            claims.append({'text': text, 'sources': ids, 'kind': kind})
        else:
            notes.append(paragraph.removeprefix('- '))
    return {'claims': claims, 'notes': notes, 'insufficient': not claims}


def source_url(section):
    accession = section.get('accession') or ''
    if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession): return None
    cik = int(accession[:10])
    document = section.get('document') or ''
    if not re.fullmatch(r'[\w.\-]+', document): document = ''
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
