"""Extract the primary SEC report into deterministic, dated filing chunks."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
import unicodedata

from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_ROOT = PROJECT_ROOT / "sec_filings"
ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")


def filing_metadata(filing_path, content, root_dir=DEFAULT_ROOT):
    """Use the SEC header, never the signing date or an inferred calendar year."""
    path = Path(filing_path).resolve()
    accession = path.parent.name
    filing_type = path.parent.parent.name
    ticker = path.parent.parent.parent.name.upper()
    if path.parent.parent.parent.parent.name != "sec-edgar-filings":
        raise ValueError(f"Unexpected SEC directory structure: {path}")
    if not ACCESSION.fullmatch(accession) or filing_type not in {"10-K", "10-Q"}:
        raise ValueError(f"Invalid filing identity: {path}")
    header_match = re.search(r"<SEC-HEADER>(.*?)</SEC-HEADER>", content, re.I | re.S)
    if not header_match:
        raise ValueError(f"Missing SEC header: {path}")
    header = header_match.group(1)

    def field(label):
        match = re.search(rf"^\s*{re.escape(label)}:\s*([^\r\n]+)", header, re.M)
        if not match:
            raise ValueError(f"Missing {label} in {path}")
        return match.group(1).strip()

    if field("ACCESSION NUMBER") != accession or field("CONFORMED SUBMISSION TYPE") != filing_type:
        raise ValueError(f"SEC header and directory identity disagree: {path}")
    filing_date = datetime.strptime(field("FILED AS OF DATE"), "%Y%m%d").date().isoformat()
    report_date = datetime.strptime(field("CONFORMED PERIOD OF REPORT"), "%Y%m%d").date().isoformat()
    return {
        "ticker": ticker,
        "filing_type": filing_type,
        "filing_date": filing_date,
        "report_date": report_date,
        "accession_number": accession,
        "source": path.relative_to(Path(root_dir).resolve()).as_posix(),
    }


def primary_document(content, filing_type):
    """Exclude EX-31/32 certifications, exhibits, graphics and XBRL documents."""
    reports = []
    for document in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", content, re.I | re.S):
        kind = re.search(r"^\s*<TYPE>\s*([^\r\n<]+)", document, re.I | re.M)
        if not kind or kind.group(1).strip() != filing_type:
            continue
        filename = re.search(r"^\s*<FILENAME>\s*([^\r\n<]+)", document, re.I | re.M)
        body = re.search(r"<TEXT>(.*?)</TEXT>", document, re.I | re.S)
        if not filename or not body:
            raise ValueError("Primary filing document is missing its filename or body.")
        reports.append((filename.group(1).strip(), body.group(1)))
    if len(reports) != 1:
        raise ValueError(f"Expected one primary {filing_type} document; found {len(reports)}.")
    return reports[0]


def extract_report_text(document):
    soup = BeautifulSoup(document, "html.parser")
    for tag in list(soup.find_all(True)):
        if not tag.name:  # An ancestor may already have been removed.
            continue
        style = re.sub(r"\s+", "", tag.get("style", "")).lower()
        if (tag.name in {"head", "script", "style", "nav", "header", "footer", "ix:header", "ix:hidden"}
                or tag.has_attr("hidden") or "display:none" in style):
            tag.decompose()
    for table in list(soup.find_all("table")):
        if not table.name:
            continue
        text = table.get_text(" ", strip=True)
        if (len(text) < 6000 and len(table.select('a[href^="#"]')) >= 3
                and len(re.findall(r"\bItem\s+\d", text, re.I)) >= 3):
            table.decompose()  # Table of contents, not a financial table.

    # Mark block boundaries, then visit text nodes once. Calling get_text on
    # every nested div/span/table used to duplicate the same paragraphs repeatedly.
    for tag in soup.find_all(["p", "div", "table", "tr", "h1", "h2", "h3", "h4", "li", "br"]):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = []
    for line in soup.get_text(" ").splitlines():
        line = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line)).strip()
        if not line:
            continue
        if re.fullmatch(r".{0,100}\|\s*(?:Q[1-4]\s+)?\d{4}\s+Form\s+10-[KQ]\s*\|\s*\d+", line, re.I):
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)
    text = "\n\n".join(lines)

    # A real signature section follows the substantive report. Do not cut at
    # a contents-page entry or at a discussion mentioning signatures.
    signatures = list(re.finditer(r"^SIGNATURES\s*$", text, re.I | re.M))
    if signatures:
        section = signatures[-1]
        tail = text[section.end():section.end() + 3000]
        if re.search(r"pursuant to the requirements|duly caused|/s/", tail, re.I):
            text = text[:section.start()]
    # Investor-website directions are not fundamental analysis. Only remove
    # this clearly bounded section when the next report item is present.
    available = re.search(r"^Available Information\s*$", text, re.I | re.M)
    if available:
        next_item = re.search(r"^Item\s+\d", text[available.end():], re.I | re.M)
        if next_item and next_item.start() < 6000:
            end = available.end() + next_item.start()
            text = text[:available.start()] + text[end:]
    return text.strip()


def chunk_filing(filing_path, root_dir=DEFAULT_ROOT):
    content = Path(filing_path).read_text(encoding="utf-8")
    metadata = filing_metadata(filing_path, content, root_dir)
    document_name, document = primary_document(content, metadata["filing_type"])
    metadata["document_name"] = document_name
    text = extract_report_text(document)
    if len(text) < 100:
        raise ValueError(f"No substantive report text in {filing_path}")
    splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=300)
    chunks = []
    seen = set()
    for chunk in splitter.split_text(text):
        if chunk in seen:
            continue
        seen.add(chunk)
        number = len(chunks)
        chunks.append({
            **metadata,
            "chunk_number": number,
            "chunk_id": f"{metadata['ticker']}_{metadata['filing_type']}_{metadata['accession_number']}_{number:05d}",
            "content": chunk,
        })
    return chunks


def process_all_filings(root_dir=DEFAULT_ROOT, tickers=None, output_file=None):
    root_dir = Path(root_dir).resolve()
    selected = {ticker.upper() for ticker in tickers} if tickers else None
    # A filtered run gets its own output by default, avoiding accidental
    # replacement of the multi-company upload input with one company's chunks.
    if output_file is None:
        suffix = "_" + "_".join(sorted(selected)) if selected else "_CLEAN"
        output_file = PROJECT_ROOT / f"processed_chunks{suffix}.json"
    output_file = Path(output_file).resolve()
    files = sorted((root_dir / "sec-edgar-filings").glob("*/*/*/full-submission.txt"))
    files = [p for p in files if p.parent.parent.name in {"10-K", "10-Q"}
             and (selected is None or p.parent.parent.parent.name.upper() in selected)]
    if not files:
        raise ValueError(f"No matching SEC filings in {root_dir}. Run data collection first.")
    if selected:
        missing = selected - {p.parent.parent.parent.name.upper() for p in files}
        if missing:
            raise ValueError(f"No downloaded filings for: {', '.join(sorted(missing))}")
    chunks = []
    for path in files:
        result = chunk_filing(path, root_dir)
        chunks.extend(result)
        print(f"{result[0]['ticker']} {result[0]['filing_type']} {result[0]['filing_date']} "
              f"{result[0]['accession_number']}: {len(result)} chunks", flush=True)
    ids = [chunk["chunk_id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate chunk IDs detected; output was not written.")
    # Publish only a complete, validated dataset, never a partially written JSON.
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_file.parent,
                                     suffix=".tmp", delete=False) as target:
        temporary = Path(target.name)
        json.dump(chunks, target, indent=2, ensure_ascii=False)
        target.write("\n")
    temporary.replace(output_file)
    print(f"Processed {len(files)} filings into {len(chunks)} unique chunks: {output_file}")
    return chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--tickers", nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    process_all_filings(args.input_dir, args.tickers, args.output)
