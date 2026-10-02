import unittest
from backend.presentation import present_answer, source_url

class PresentationTests(unittest.TestCase):
    def test_keeps_verified_numbers_period_and_source(self):
        source={'source_id':'AAPL:F1','filing_type':'10-Q'}
        result=present_answer('- Cash was $39,544 million as of June 27, 2026. (AAPL, 10-Q, filed 2026-07-31, accession 0000320193-26-000020, AAPL:F1)',[source])
        self.assertEqual(result['claims'][0]['text'],'Cash was $39,544 million as of June 27, 2026.')
        self.assertEqual(result['claims'][0]['sources'],['AAPL:F1'])
        self.assertFalse(result['insufficient'])
    def test_insufficient_stays_insufficient(self):
        result=present_answer('The supplied evidence is insufficient.',[])
        self.assertTrue(result['insufficient'])
        self.assertEqual(result['claims'],[])
    def test_sec_url_uses_validated_accession(self):
        self.assertEqual(source_url({'accession':'0000320193-26-000020','document':'aapl.htm'}),'https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl.htm')
        self.assertIsNone(source_url({'accession':'../../.env'}))

if __name__=='__main__':unittest.main()
