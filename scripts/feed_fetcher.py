"""Collect English RSS/Atom headlines. Preserve data on failure; publish source health."""
import concurrent.futures
import hashlib
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data/signals.json'
STATUS = ROOT / 'data/collection-status.json'
FEEDS = {
    'CEEnergyNews': 'https://ceenergynews.com/feed/',
    'ESS News': 'https://www.ess-news.com/feed/',
    'pv magazine': 'https://www.pv-magazine.com/feed/',
    'Notes From Poland': 'https://notesfrompoland.com/feed/',
    'Baltic Wind': 'https://balticwind.eu/feed/',
    'Renewables Now': 'https://renewablesnow.com/news/rss/',
    'World Nuclear News': 'https://www.world-nuclear-news.org/rss',
}
POLAND = re.compile(r'\bpoland\b|\bpolish\b|\bpge\b|tauron|\benea\b|energa|orlen|ze pak|baltica|bałtyk|baltyk|lubiatowo|warsaw', re.I)
POWER = re.compile(r'power|energy|electric|grid|wind|solar|\bpv\b|batter|storage|bess|gas|ccgt|ocgt|nuclear|smr|coal|chp|heat|hydrogen|capacity|tariff', re.I)
COS = {'PGE': r'\bpge\b', 'ENEA': r'\benea\b', 'ENERGA': r'energa', 'ORLEN': r'orlen', 'TAURON': r'tauron',
       'ZEPAK': r'ze pak', 'PEJ': r'\bpej\b|polskie elektrownie j', 'POLENERGIA': r'polenergia',
       'AXPO': r'\baxpo\b', 'ENGIE': r'\bengie\b', 'FORTUM': r'fortum', 'EQUINOR': r'equinor',
       'ORSTED': r'ørsted|orsted', 'RWE': r'\brwe\b', 'TOTAL': r'totalenergies', 'EDPR': r'\bedpr?\b'}
ATOM = '{http://www.w3.org/2005/Atom}'


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()


def parse_date(value):
    try:
        stamp = parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError):
        try:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, TypeError, AttributeError):
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime('%Y-%m-%d')


def parse_feed(name, body):
    root = ET.fromstring(body)
    if root.tag not in ('rss', 'feed', ATOM + 'feed', '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF'):
        raise ValueError('Response is not an RSS/Atom feed')
    records = []
    entries = list(root.iter('item')) + list(root.iter(ATOM + 'entry'))
    today = datetime.now(timezone.utc).date().isoformat()
    for item in entries:
        atom = item.tag == ATOM + 'entry'
        prefix = ATOM if atom else ''
        title = clean(item.findtext(prefix + 'title'))
        if atom:
            link = next((el.get('href', '') for el in item.findall(ATOM + 'link') if el.get('rel', 'alternate') == 'alternate'), '')
        else:
            link = item.findtext('link') or ''
        link = link.strip()
        desc = clean(item.findtext(prefix + ('summary' if atom else 'description')) or item.findtext(prefix + 'content'))
        date = parse_date(item.findtext(prefix + ('published' if atom else 'pubDate')) or item.findtext(prefix + 'updated') or '')
        if not title or not link.startswith('https://') or not date or not '2024-01-01' <= date <= today:
            continue
        hay = title + ' ' + desc
        if not (POLAND.search(hay) and POWER.search(hay)):
            continue
        records.append({
            'id': 'live-' + hashlib.md5(link.encode()).hexdigest()[:10],
            'date': date, 'title': title, 'summary': ' '.join(desc.split()[:70]) + ('…' if len(desc.split()) > 70 else ''),
            'links': [{'label': name + ' — article', 'url': link, 'type': 'press'}],
            'cos': [key for key, pattern in COS.items() if re.search(pattern, hay, re.I)] or ['ALL'],
            'publisher': name, 'lang': 'en', 'region': 'National', 'reviewed': False,
        })
    return records, len(entries)


def fetch(name, url):
    request = urllib.request.Request(url, headers={'User-Agent': 'PolandPowerPulse/1.0 (+https://neelamgulati7788.github.io/poland-power-pulse-v34/)', 'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml'})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(5 * 1024 * 1024 + 1)
    if len(body) > 5 * 1024 * 1024:
        raise ValueError('Feed exceeds 5 MiB limit')
    return parse_feed(name, body)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def collect(fetcher=fetch):
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'updated': None, 'signals': []}
    old = {item['id']: item for item in previous.get('signals', [])}
    prior_ids = set(old)
    health = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tasks = {pool.submit(fetcher, name, url): (name, url) for name, url in FEEDS.items()}
        for task in concurrent.futures.as_completed(tasks):
            name, url = tasks[task]
            try:
                items, total = task.result()
                for item in items:
                    old[item['id']] = item
                row = {'source': name, 'url': url, 'status': 'success', 'entriesRead': total, 'matched': len(items)}
                print(f'OK {name}: {len(items)} matching / {total} entries', flush=True)
            except Exception as error:
                row = {'source': name, 'url': url, 'status': 'error', 'error': str(error)[:250]}
                print(f'ERROR {name}: {error}', flush=True)
            health.append(row)
    successes = sum(row['status'] == 'success' for row in health)
    records = sorted(old.values(), key=lambda item: (item['date'], item['id']), reverse=True)[:400]
    if successes:
        write_json(OUT, {'updated': now, 'signals': records})
    status = {
        'checkedAt': now, 'lastSuccessfulCollectionAt': now if successes else previous.get('updated'),
        'status': 'success' if successes == len(FEEDS) else 'partial' if successes else 'error',
        'successfulSources': successes, 'totalSources': len(FEEDS),
        'newItems': len(set(old) - prior_ids), 'retainedItems': len(records),
        'latestPublicationDate': max((item['date'] for item in records), default=None),
        'sources': sorted(health, key=lambda row: row['source']),
        'scope': 'English RSS/Atom headlines only; recent feed windows; no automated translation or analyst review.',
    }
    write_json(STATUS, status)
    print(json.dumps({key: value for key, value in status.items() if key != 'sources'}, ensure_ascii=False))
    return 0 if successes else 1


if __name__ == '__main__':
    sys.exit(collect())
