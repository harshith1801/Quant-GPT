"""Grounding safety checks; offline, no provider calls."""
import json
import unittest
from unittest.mock import Mock
from answer_grounding import format_evidence, supported_drafts, render_verified, complete_balance_evidence


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(ticker='TEST', filing_type='10-Q', filing_date='2026-07-31',
                           accession='example', source_id='TEST:F1',
                           text='In millions. Cash and cash equivalents 39,544 35,934.')
        self.sources = {'TEST:F1': self.source}
        self.claim = dict(text='Cash and cash equivalents were 39,544 million.',
                          source_id='TEST:F1', quote=self.source['text'])

    def test_cash_evidence_uses_exact_balance_line_and_same_accession(self):
        meta = dict(ticker='TEST', filing_type='10-Q', filing_date='2026-07-31',
                    accession_number='one', source='report.txt')
        seed = dict(meta, chunk_id='TEST_one_00004', content='Statement of equity')
        exact = dict(meta, content='Balance sheet, in millions, June 30, 2026\nCash and cash equivalents $ 39,544')
        wrong = dict(exact, accession_number='other')
        index = Mock()
        index.fetch.return_value = {'vectors': {
            'TEST_one_00003': {'metadata': exact},
            'TEST_one_00005': {'metadata': wrong},
        }}
        chosen = complete_balance_evidence('How much cash and cash equivalents?', [seed], index)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]['chunk_id'], 'TEST_one_00003')
        self.assertEqual(chosen[0]['content'], exact['content'])

    def test_fabricated_quotes_and_source_ids_rejected(self):
        draft = {'claims': [self.claim, dict(self.claim, source_id='OTHER:F1'),
                             dict(self.claim, quote='Cash and cash equivalents 26,777 million')]}
        self.assertEqual(supported_drafts(draft, self.sources), [self.claim])

    def test_missing_rejected_or_duplicate_verdicts_fail_closed(self):
        for verdicts in [[], [{'claim_index': 0, 'supported': False}],
                         [{'claim_index': 0, 'supported': 'true'}],
                         [{'claim_index': 0, 'supported': True}]*2]:
            answer = render_verified([self.claim], {'verdicts': verdicts}, self.sources)
            self.assertIn('insufficient', answer)
            self.assertNotIn('39,544', answer)

    def test_approved_claim_keeps_value_and_source(self):
        answer = render_verified([self.claim], {'verdicts': [{'claim_index': 0, 'supported': True}]}, self.sources)
        self.assertIn('39,544 million', answer)
        self.assertIn('10-Q, filed 2026-07-31, accession example', answer)

    def test_evidence_preserves_text_and_provenance(self):
        chunk = dict(ticker='TEST', filing_type='10-Q', filing_date='2026-07-31',
                     accession_number='accession', report_date='2026-06-30',
                     source='original.txt', document_name='report.htm', chunk_id='id',
                     content='Cash\n1,234\nTable continues')
        section = json.loads(format_evidence([chunk], 'latest'))['sections'][0]
        self.assertEqual(section['text'], chunk['content'])
        self.assertEqual(section['accession'], 'accession')
        self.assertEqual(section['report_period_end'], '2026-06-30')
        self.assertIn('mid-table', section['warning'])


if __name__ == '__main__':
    unittest.main()
