"""Offline regression tests for filing identity, extraction, and upload validation."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_script(filename):
    spec = importlib.util.spec_from_file_location(filename[:-3], ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


processing = load_script("2_processing.py")
upload = load_script("4_upload_to_pinecone.py")


class FilingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def filing(self, accession="0000320193-25-000079", ticker="AAPL"):
        path = self.root / "sec-edgar-filings" / ticker / "10-K" / accession / "full-submission.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'''<SEC-HEADER>
ACCESSION NUMBER: {accession}
CONFORMED SUBMISSION TYPE: 10-K
FILED AS OF DATE: 20251031
CONFORMED PERIOD OF REPORT: 20250927
</SEC-HEADER>
<DOCUMENT>
<TYPE>10-K
<FILENAME>annual.htm
<TEXT><html><body>
<ix:header><ix:hidden>HIDDEN XBRL MARKER</ix:hidden></ix:header>
<div><p>UNIQUE BUSINESS MARKER: Product demand and litigation can affect financial results.</p>
<p>{'Substantive business risk information. ' * 90}</p></div>
<table><tr><td>Net sales</td><td><div>123456789</div></td></tr></table>
<h2>SIGNATURES</h2><p>Pursuant to the requirements, /s/ SIGNATURE MARKER</p>
</body></html></TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-32.1
<FILENAME>certification.htm
<TEXT><p>I certify: EXHIBIT CERTIFICATION MARKER</p></TEXT>
</DOCUMENT>''', encoding="utf-8")
        return path

    def test_unique_deterministic_ids_and_metadata(self):
        first = self.filing()
        second = self.filing("0000320193-24-000123")
        a = processing.chunk_filing(first, self.root)
        b = processing.chunk_filing(second, self.root)
        self.assertEqual(a, processing.chunk_filing(first, self.root))
        self.assertFalse({c["chunk_id"] for c in a} & {c["chunk_id"] for c in b})
        self.assertEqual(upload.validate_chunks(a + b), 2)
        self.assertEqual(a[0]["filing_date"], "2025-10-31")
        self.assertEqual(a[0]["report_date"], "2025-09-27")
        self.assertEqual(a[0]["document_name"], "annual.htm")
        self.assertEqual(a[0]["chunk_number"], 0)
        self.assertEqual(upload.vector_metadata(a[0])["accession_number"], first.parent.name)
        self.assertIn("filing_date", upload.vector_metadata(a[0]))

    def test_primary_document_only_and_single_text_traversal(self):
        path = self.filing()
        _, document = processing.primary_document(path.read_text(), "10-K")
        text = processing.extract_report_text(document)
        self.assertEqual(text.count("UNIQUE BUSINESS MARKER"), 1)
        self.assertIn("123456789", text)  # Financial table cells must survive.
        for marker in ["SIGNATURE MARKER", "HIDDEN XBRL MARKER", "EXHIBIT CERTIFICATION MARKER"]:
            self.assertNotIn(marker, text)
        self.assertIn("litigation", text)

    def test_reject_header_mismatch_or_missing_date(self):
        path = self.filing()
        original = path.read_text()
        for content in [original.replace("FILED AS OF DATE: 20251031", ""),
                        original.replace("ACCESSION NUMBER: 0000320193-25-000079", "ACCESSION NUMBER: 0000320193-24-000123")]:
            path.write_text(content)
            with self.assertRaises(ValueError):
                processing.chunk_filing(path, self.root)

    def test_filter_isolation_and_repeatable_output(self):
        self.filing()
        self.filing(ticker="MSFT")
        output = self.root / "aapl.json"
        with contextlib.redirect_stdout(io.StringIO()):
            processing.process_all_filings(self.root, ["AAPL"], output)
            before = output.read_bytes()
            processing.process_all_filings(self.root, ["AAPL"], output)
        self.assertEqual(before, output.read_bytes())
        self.assertEqual({c["ticker"] for c in json.loads(before)}, {"AAPL"})

    def test_failed_processing_preserves_previous_output(self):
        path = self.filing()
        path.write_text(path.read_text().replace("FILED AS OF DATE: 20251031", ""))
        output = self.root / "existing.json"
        output.write_text("previous dataset")
        with self.assertRaises(ValueError):
            processing.process_all_filings(self.root, ["AAPL"], output)
        self.assertEqual(output.read_text(), "previous dataset")

    def test_upload_validator_rejects_collisions_legacy_ids_and_missing_metadata(self):
        chunks = processing.chunk_filing(self.filing(), self.root)
        bad_sets = [chunks + [chunks[0]]]
        for field, value in [("chunk_id", "AAPL_10-K_0"), ("filing_date", ""),
                             ("source", "wrong/source.txt"), ("chunk_number", -1)]:
            changed = copy.deepcopy(chunks)
            changed[0][field] = value
            bad_sets.append(changed)
        for bad in bad_sets:
            with self.assertRaises(ValueError):
                upload.validate_chunks(bad)

    def test_default_uploader_is_local_only(self):
        output = self.root / "chunks.json"
        output.write_text(json.dumps(processing.chunk_filing(self.filing(), self.root)))
        with patch("sys.argv", ["4_upload_to_pinecone.py", "--input", str(output)]), \
                patch.dict("sys.modules", {"pinecone": None, "sentence_transformers": None}), \
                contextlib.redirect_stdout(io.StringIO()) as log:
            upload.main()
        self.assertIn("No model was loaded and no Pinecone request was made", log.getvalue())


if __name__ == "__main__":
    unittest.main()
