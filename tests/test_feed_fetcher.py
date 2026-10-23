import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('feed', Path(__file__).resolve().parents[1] / 'scripts/feed_fetcher.py')
feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed)


class CollectionTests(unittest.TestCase):
    def test_rss_keeps_relevant_and_rejects_unsafe_urls(self):
        rss = b'''<rss><channel><item><title>Poland wind grid contract</title><link>https://example.com/a</link><description>Polish power investment</description><pubDate>Thu, 22 Oct 2026 10:00:00 GMT</pubDate></item><item><title>Poland wind project</title><link>javascript:alert(1)</link><pubDate>Thu, 22 Oct 2026 10:00:00 GMT</pubDate></item><item><title>French solar project</title><link>https://example.com/b</link><pubDate>Thu, 22 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'''
        items, total = feed.parse_feed('Test', rss)
        self.assertEqual(total, 3)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Poland wind grid contract')
        self.assertFalse(items[0]['reviewed'])

    def test_atom_and_invalid_dates(self):
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Poland nuclear plant</title><link href="https://example.com/a"/><updated>2026-10-22T12:00:00Z</updated></entry></feed>'''
        items, total = feed.parse_feed('Test', atom)
        self.assertEqual((len(items), total), (1, 1))
        self.assertIsNone(feed.parse_date('2026-99-99'))
        with self.assertRaises(ValueError):
            feed.parse_feed('Test', b'<html><body>error</body></html>')

    def test_outage_preserves_feed_and_success_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            out, status = Path(d)/'signals.json', Path(d)/'status.json'
            original = '{"updated":"2026-10-20T12:00:00Z","signals":[]}'
            out.write_text(original)
            def fail(name, url):
                raise ValueError('unavailable')
            with patch.object(feed, 'OUT', out), patch.object(feed, 'STATUS', status), patch.object(feed, 'FEEDS', {'A':'https://example.com'}):
                self.assertEqual(feed.collect(fail), 1)
            self.assertEqual(out.read_text(), original)
            report = json.loads(status.read_text())
            self.assertEqual(report['status'], 'error')
            self.assertEqual(report['lastSuccessfulCollectionAt'], '2026-10-20T12:00:00Z')

    def test_partial_success_retains_prior_items_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            out, status = Path(d)/'signals.json', Path(d)/'status.json'
            old = {'id':'old', 'date':'2026-10-20', 'title':'Existing'}
            out.write_text(json.dumps({'updated':'2026-10-20T00:00:00Z','signals':[old]}))
            def partial(name, url):
                if name == 'B': raise ValueError('unavailable')
                return [{'id':'new','date':'2026-10-22','title':'New'}] * 2, 2
            with patch.object(feed, 'OUT', out), patch.object(feed, 'STATUS', status), patch.object(feed, 'FEEDS', {'A':'https://example.com','B':'https://example.org'}):
                self.assertEqual(feed.collect(partial), 0)
            self.assertEqual(len(json.loads(out.read_text())['signals']), 2)
            report = json.loads(status.read_text())
            self.assertEqual((report['status'], report['newItems']), ('partial', 1))

if __name__ == '__main__':
    unittest.main()
