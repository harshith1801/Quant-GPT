"""Offline tests for date selection and bounded recency ranking."""
import unittest
from datetime import date
from unittest.mock import Mock
from types import SimpleNamespace
import numpy as np
from filing_retrieval import latest_form, retrieve, filing_catalog


class RetrievalTests(unittest.TestCase):
    def test_catalog_handles_sdk_ids_and_all_pages(self):
        index = Mock()
        index.list.return_value = [[SimpleNamespace(id='TEST_a')], ['TEST_b']]
        index.fetch.side_effect = [
            {'vectors': {'TEST_a': {'metadata': dict(ticker='TEST', filing_type='10-Q', filing_date='2024-01-01', accession_number='a')}}},
            {'vectors': {'TEST_b': {'metadata': dict(ticker='TEST', filing_type='10-Q', filing_date='2025-01-01', accession_number='b')}}},
        ]
        catalog = filing_catalog(index, 'TEST')
        self.assertEqual(len(catalog), 2)
        self.assertEqual(index.fetch.call_args_list[0].kwargs['ids'], ['TEST_a'])
        self.assertEqual(max(f['filing_date'] for f in catalog), '2025-01-01')

    def test_period_intent_and_historical_opt_out(self):
        self.assertEqual(latest_form('latest quarterly results'), '10-Q')
        self.assertEqual(latest_form('recent annual results'), '10-K')
        self.assertIsNone(latest_form('current business risks'))
        self.assertIsNone(latest_form('compare quarterly results in 2023 and 2024'))

    def test_latest_selected_from_metadata_for_any_ticker(self):
        for ticker in ['AAPL', 'MSFT', 'NVDA']:
            for form, query in [('10-Q', 'latest quarterly results'), ('10-K', 'recent annual results')]:
                index, model = Mock(), Mock()
                model.encode.return_value = np.array([1.0])
                index.query.return_value = {'matches': []}
                catalog = [dict(filing_type=form, filing_date=d, accession_number=a)
                           for d, a in [('2024-01-01', 'older'), ('2025-01-01', 'newer')]]
                retrieve(query, ticker, model, index, catalog)
                self.assertEqual(index.query.call_args.kwargs['filter'], dict(
                    ticker=ticker, filing_type=form, filing_date='2025-01-01', accession_number='newer'))

    def test_recency_breaks_near_ties_but_preserves_strong_historical_evidence(self):
        index, model = Mock(), Mock()
        model.encode.return_value = np.array([1.0])
        index.query.return_value = {'matches': [
            {'id': 'strong-old', 'score': .8, 'metadata': {'filing_date': '2020-01-01'}},
            {'id': 'near-old', 'score': .61, 'metadata': {'filing_date': '2020-01-01'}},
            {'id': 'recent', 'score': .60, 'metadata': {'filing_date': date.today().isoformat()}},
        ]}
        sources, _ = retrieve('business risks', 'TEST', model, index, [], 3)
        self.assertEqual([s['chunk_id'] for s in sources], ['strong-old', 'recent', 'near-old'])
        sources, _ = retrieve('historical business risks in 2020', 'TEST', model, index, [], 3)
        self.assertEqual([s['chunk_id'] for s in sources], ['strong-old', 'near-old', 'recent'])

    def test_missing_dated_form_does_not_silently_use_old_other_form(self):
        index = Mock()
        sources, message = retrieve('latest quarterly results', 'TEST', Mock(), index, [])
        self.assertEqual(sources, [])
        self.assertIn('cannot be verified', message)
        index.query.assert_not_called()


if __name__ == '__main__':
    unittest.main()
