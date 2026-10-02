import unittest
from unittest.mock import Mock, patch
import requests
import market_data as md

HISTORY = {'Time Series (Daily)': {
    '2026-09-30': {'4. close': '110', '5. volume': '222'},
    '2026-09-28': {'4. close': '90', '5. volume': '111'},
    '2026-09-29': {'4. close': '100', '5. volume': '333'},
}}


class MarketTests(unittest.TestCase):
    def test_fields_share_latest_record_even_if_unsorted(self):
        quote, chart = md.parse_stock(HISTORY)
        self.assertEqual((quote['date'], quote['price'], quote['volume']), ('2026-09-30', 110, 222))
        self.assertEqual(quote['previous_date'], '2026-09-29')
        self.assertAlmostEqual(quote['change_percent_float'], .1)
        self.assertEqual(quote['change_percent_str'], '+10.00%')
        self.assertEqual(chart.iloc[-1]['Price'], quote['price'])

    def test_api_limit_and_error_not_empty_news(self):
        for payload, expected in [({'Information': '25 requests per day rate limit'}, 'rate_limited'),
                                  ({'Note': 'API call frequency exceeded'}, 'rate_limited'),
                                  ({'Error Message': 'Invalid symbol'}, 'api_error'),
                                  ({'Information': 'Premium endpoint'}, 'api_error')]:
            status, message = md.api_status(payload)
            result = md.parse_news(payload, 'AAPL', status, message)
            self.assertEqual(result['status'], expected)
            self.assertFalse(result['available'])
            self.assertNotIn('Neutral', result['overall_sentiment_label'])
            self.assertNotIn('No recent news', result['overall_sentiment_label'])
        self.assertEqual(md.parse_news({'feed': []}, 'AAPL')['status'], 'no_news')
        self.assertEqual(md.parse_news({}, 'AAPL')['status'], 'api_error')

    def test_success_uses_only_available_ticker_scores(self):
        feed = {'feed': [{'title': 'AAPL article', 'time_published': '20261001T120000',
                         'ticker_sentiment': [{'ticker': 'AAPL', 'ticker_sentiment_score': '.2', 'ticker_sentiment_label': 'Bullish'}]},
                        {'title': 'No sentiment', 'ticker_sentiment': []}]}
        result = md.parse_news(feed, 'AAPL')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['overall_sentiment_label'], 'Positive')
        self.assertEqual(result['articles'][1]['sentiment_label'], 'Unavailable')
        self.assertEqual(result['articles'][0]['published_at'], '20261001T120000')

    def test_provider_cannot_exceed_requested_article_limit(self):
        result = md.parse_news({'feed': [{'title': 'AAPL news', 'ticker_sentiment': []}] * 50}, 'AAPL')
        self.assertEqual(len(result['articles']), 10)

    def test_shared_cache_reuses_success_and_failure(self):
        md.cached_stock.clear()
        md.cached_news.clear()
        with patch.object(md, 'fetch', return_value=(HISTORY, 'ok', '', 'checked')) as fetch:
            for _ in range(3): md.cached_stock('AAPL', 'test-key')
            self.assertEqual(fetch.call_count, 1)
        with patch.object(md, 'fetch', return_value=({}, 'rate_limited', 'rate limit', 'checked')) as fetch:
            for _ in range(3): self.assertEqual(md.cached_news('AAPL', 'test-key')['status'], 'rate_limited')
            self.assertEqual(fetch.call_count, 1)
        md.cached_stock.clear()
        md.cached_news.clear()

    def test_transport_errors_do_not_leak_keys_or_become_empty_news(self):
        with patch.object(md.requests, 'get', side_effect=requests.RequestException('secret-key')):
            _, status, message, _ = md.fetch('NEWS_SENTIMENT', 'AAPL', 'secret-key')
        self.assertEqual(status, 'api_error')
        self.assertNotIn('secret-key', message)
        with patch.object(md.requests, 'get', return_value=Mock(status_code=429)):
            _, status, _, _ = md.fetch('NEWS_SENTIMENT', 'AAPL', 'secret-key')
        self.assertEqual(status, 'rate_limited')


if __name__ == '__main__': unittest.main()
