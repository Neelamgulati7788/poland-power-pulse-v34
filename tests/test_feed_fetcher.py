import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('feed',Path(__file__).resolve().parents[1]/'scripts/feed_fetcher.py')
feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed)
SOURCE = {'id':'1','source':'Test','website':'https://example.com','group':'International media','language':'PL/EN','polandScoped':False,'domains':['example.com'],'routes':[]}

class CollectionTests(unittest.TestCase):
    def test_rss_relevance_urls_and_polish_originals(self):
        body = '<rss><channel><item><title>PGE wybrała wykonawcę magazynów energii</title><link>https://example.com/a</link><pubDate>Fri, 23 Oct 2026 09:00:00 GMT</pubDate></item><item><title>Poland wind contract</title><link>javascript:alert(1)</link><pubDate>Fri, 23 Oct 2026 09:00:00 GMT</pubDate></item></channel></rss>'.encode()
        records,total=feed.parse_feed(SOURCE,body,'PL/EN')
        self.assertEqual((total,len(records)),(2,1))
        self.assertEqual(records[0]['lang'],'pl')
        self.assertFalse(records[0]['translated'])
        self.assertEqual(records[0]['title_pl'],records[0]['title'])

    def test_english_is_not_mislabelled_polish(self):
        record=feed.record(SOURCE,'Poland wind power project','https://example.com/a','2026-10-23',lang='PL')
        self.assertEqual(record['lang'],'en')

    def test_indexed_domain_verification_and_suffix(self):
        body=b'<rss><channel><item><title>Poland wind power project - Test</title><link>https://news.google.com/rss/articles/ABC</link><source url="https://example.com">Test</source><pubDate>Fri, 23 Oct 2026 09:00:00 GMT</pubDate></item><item><title>Poland wind</title><link>https://news.google.com/rss/articles/DEF</link><source url="https://unrelated.example">Other</source><pubDate>Fri, 23 Oct 2026 09:00:00 GMT</pubDate></item></channel></rss>'
        records,total=feed.parse_feed(SOURCE,body,'EN','google')
        self.assertEqual((total,len(records)),(2,1))
        self.assertEqual(records[0]['title'],'Poland wind power project')
        self.assertEqual(records[0]['evidenceLevel'],'indexed_headline')

    def test_rejects_error_html_and_bad_dates(self):
        with self.assertRaises(ValueError):feed.parse_feed(SOURCE,b'<html><body>Unavailable</body></html>')
        self.assertIsNone(feed.parse_date('2026-99-99'))

    def test_merge_prefers_direct_source_and_retains_source_ids(self):
        a={'id':'a','title':'Poland wind','date':'2026-10-23','discoveryMethod':'google','sourceIds':['1']}
        b={**a,'id':'b','discoveryMethod':'rss','sourceIds':['2']}
        items=feed.merge_records([a],[b])
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['id'],'b')
        self.assertEqual(items[0]['sourceIds'],['1','2'])

    def test_total_outage_preserves_published_records(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'signals.json';status=root/'status.json';registry=root/'sources.json'
            original='{"updated":"2026-10-20T00:00:00Z","signals":[]}'
            out.write_text(original);registry.write_text(json.dumps({'requestedRows':1,'sources':[SOURCE]}))
            def fail(source,start):raise ValueError('unavailable')
            with patch.object(feed,'OUT',out),patch.object(feed,'STATUS',status),patch.object(feed,'REGISTRY',registry):
                self.assertEqual(feed.collect(fail),1)
            self.assertEqual(out.read_text(),original)
            report=json.loads(status.read_text())
            self.assertEqual(report['successfulSources'],0)
            self.assertEqual(report['lastSuccessfulCollectionAt'],'2026-10-20T00:00:00Z')

if __name__=='__main__':unittest.main()
