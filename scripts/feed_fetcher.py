"""Collect Polish/English public headlines from the source workbook registry.
Index discovery, direct-feed coverage, API sampling and failures remain distinct.
"""
import concurrent.futures
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data/signals.json'
STATUS = ROOT / 'data/collection-status.json'
REGISTRY = ROOT / 'data/sources.json'
MAX_BYTES = 16 * 1024 * 1024
ATOM = '{http://www.w3.org/2005/Atom}'
POLAND = re.compile(r'poland|polish|polsk|\bpge\b|tauron|\benea\b|energa|orlen|ze pak|baltica|bałtyk|baltyk|lubiatowo|warsaw|warszaw|bełchat|kozienic|ostrołęk|grudziądz|żarnowiec|rybnik|pątnów', re.I)
POWER = re.compile(r'\bpower\b|energ|electric|elektr|\bgrid\b|\bwind\b|wiatr|solar|fotowolt|\bpv\b|batter|\bstorage\b|magazyn.{0,20}energ|\bbess\b|\bgas\b|\bgaz(?:\b|u\b|em\b|ow|ociąg|own)|ccgt|ocgt|nuclear|jądrow|\bsmr\b|\bcoal\b|węgl|\bchp\b|\bheat|ciepł|hydrogen|wodor|capacity.market|tariff|taryf|\bpge\b|tauron|\benea\b|energa|orlen|polenergia|\bpej\b|\bpse\b|\btge\b|biometan|\bmw\b|\bmwh\b', re.I)
IGNORE = re.compile(r'oferta pracy|rekrutacj|kariera|inżynierka/|specjalist[ak].*ds\.|stażysta|job opening|vacancy|career opportunity|transakcj.*art\. 19|persons discharging managerial|udzieleniu pełnomocnictwa', re.I)
COS = {'PGE': r'\bpge\b', 'ENEA': r'\benea\b', 'ENERGA': r'energa', 'ORLEN': r'orlen', 'TAURON': r'tauron',
       'ZEPAK': r'ze pak', 'PEJ': r'\bpej\b|polskie elektrownie j', 'POLENERGIA': r'polenergia',
       'AXPO': r'\baxpo\b', 'ENGIE': r'\bengie\b', 'FORTUM': r'fortum', 'EQUINOR': r'equinor',
       'ORSTED': r'ørsted|orsted', 'RWE': r'\brwe\b', 'TOTAL': r'totalenergies', 'EDPR': r'\bedpr?\b',
       'OCEANWINDS': r'ocean winds|bc-wind', 'EDF': r'\bedf\b|dalkia'}


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()


def parse_date(value):
    try:
        stamp = parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError):
        try:
            stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (ValueError, TypeError, AttributeError):
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime('%Y-%m-%d')


def request(url, payload=None, headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Only public HTTPS endpoints are supported')
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={'User-Agent': 'PolandPowerPulse/2.0 (+https://neelamgulati7788.github.io/poland-power-pulse-v34/)',
                 'Accept': 'application/rss+xml, application/atom+xml, application/json, text/xml, */*',
                 **({'Content-Type': 'application/json'} if payload is not None else {}), **(headers or {})})
    with urllib.request.urlopen(req, timeout=40) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('Response exceeds configured 16 MiB limit')
    return body


def qurl(url, params):
    return url + '?' + urllib.parse.urlencode(params)


def relevant(source, title, excerpt):
    text = title + ' ' + ' '.join(excerpt.split()[:100])
    if IGNORE.search(title) or not POWER.search(text):
        return False
    return source.get('polandScoped', False) or bool(POLAND.search(text))


def record(source, title, url, date, excerpt='', lang='EN', kind='rss', publisher=None, publisher_url=None):
    date = parse_date(date)
    title, excerpt = clean(title), clean(excerpt)
    if not date or not '2024-01-01' <= date <= datetime.now(timezone.utc).date().isoformat():
        return None
    if not title or not str(url).startswith('https://') or not relevant(source, title, excerpt):
        return None
    # Mixed-language source rows do not imply that each article is Polish.
    is_pl = (lang.upper() == 'PL' and source.get('language') == 'PL') or bool(re.search(r'[ąćęłńóśźż]|\b(?:oraz|sprawie|Polsce|budowa|podpisano|zawarcie|wyniki|zarząd|wykonawcę)\b', title, re.I))
    text = title + ' ' + excerpt
    key = re.sub(r'\W+', ' ', title.casefold()).strip() + '|' + date + '|' + (publisher or source['source']).casefold()
    return {
        'id': 'src-' + hashlib.sha256(key.encode()).hexdigest()[:18], 'date': date, 'title': title,
        'title_pl': title if is_pl else '', 'lang': 'pl' if is_pl else 'en', 'translated': False,
        'translationStatus': 'original_polish' if is_pl else 'not_required',
        'summary': (' '.join(excerpt.split()[:45]) + ('…' if len(excerpt.split()) > 45 else '')) if excerpt and excerpt != title else
                   ('Polish original headline; English translation is not available.' if is_pl else 'Indexed headline; open the publisher article for full details.'),
        'links': [{'label': (publisher or source['source']) + (' — Google News discovery' if kind == 'google' else ' — source'), 'url': url,
                   'type': 'press' if source['group'] in ('International media', 'Polish specialist media', 'Polish business press') else 'official'}],
        'cos': [key for key, pattern in COS.items() if re.search(pattern, text, re.I)] or ['ALL'],
        'publisher': publisher or source['source'], 'publisherUrl': publisher_url or source['website'],
        'region': 'National' if POLAND.search(text) or source['group'] in ('Government & legislation','Regulators','Company disclosures','Company disclosures (ESPI)','System operators & market') else 'Unspecified / Poland-focused source',
        'reviewed': False, 'sourceIds': [source['id']], 'discoveryMethod': kind,
        'evidenceLevel': 'indexed_headline' if kind == 'google' else 'publisher_feed' if kind == 'rss' else 'official_metadata',
    }


def parse_feed(source, body, language='EN', kind='rss'):
    root = ET.fromstring(body)
    if root.tag not in ('rss', 'feed', ATOM + 'feed', '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF'):
        raise ValueError('Response is not an RSS/Atom feed')
    entries = list(root.iter('item')) + list(root.iter(ATOM + 'entry'))
    records = []
    for item in entries:
        atom = item.tag == ATOM + 'entry'
        prefix = ATOM if atom else ''
        title = item.findtext(prefix + 'title') or ''
        if atom:
            link = next((el.get('href', '') for el in item.findall(ATOM + 'link') if el.get('rel', 'alternate') == 'alternate'), '')
        else:
            link = item.findtext('link') or ''
        publisher, publisher_url = None, None
        src = item.find('source')
        if kind == 'google' and src is not None:
            publisher = clean(src.text)
            publisher_url = src.get('url', '')
            host = urllib.parse.urlsplit(publisher_url).netloc.removeprefix('www.')
            allowed = source.get('domains', [])
            if allowed and not any(host == d or host.endswith('.' + d) for d in allowed):
                continue
            if publisher and title.endswith(' - ' + publisher):
                title = title[:-(len(publisher) + 3)]
        # Google descriptions are repeated linked headlines, not an article summary.
        excerpt = '' if kind == 'google' else item.findtext(prefix + ('summary' if atom else 'description')) or item.findtext(prefix + 'content') or ''
        date = item.findtext(prefix + ('published' if atom else 'pubDate')) or item.findtext(prefix + 'updated') or ''
        r = record(source, title, link.strip(), date, excerpt, language, kind, publisher, publisher_url)
        if r:
            records.append(r)
    return records, len(entries)


def extract_language_titles(value):
    if isinstance(value, str): return value, 'EN'
    if isinstance(value, dict):
        for key in ('eng', 'en', 'pol', 'pl'):
            if value.get(key):
                text = value[key]
                return (' '.join(str(x) for x in text) if isinstance(text, list) else str(text)), ('PL' if key in ('pol','pl') else 'EN')
        return ' '.join(str(x) for x in value.values()), 'PL'
    return str(value or ''), 'PL'


def fetch_api(source, route, start):
    kind, url = route['kind'], route['url']
    data = None
    limited = False
    if kind == 'eli':
        data = json.loads(request(qurl(url, {'publisher':'DU','pubDateFrom':start,'limit':500})))
        entries = data.get('items', [])
        limited = len(entries) >= 500
        records = [record(source, x.get('title',''), 'https://eli.gov.pl/eli/' + x['ELI'] + '/ogl', x.get('promulgation') or x.get('announcementDate'), lang='PL', kind=kind) for x in entries if x.get('ELI')]
    elif kind in ('prints','processes'):
        entries = json.loads(request(url + '?limit=10000'))
        if not isinstance(entries, list): raise ValueError('Expected a Sejm metadata array')
        records = []
        for x in entries:
            date = x.get('deliveryDate') or x.get('processStartDate') or x.get('documentDate')
            if (parse_date(date) or '') < start: continue
            number = x.get('number','')
            link = 'https://www.sejm.gov.pl/Sejm10.nsf/druk.xsp?nr=' + urllib.parse.quote(str(number))
            records.append(record(source,x.get('title',''),link,date,lang='PL',kind=kind))
    elif kind == 'pse_data':
        data = json.loads(request(url))
        if not isinstance(data, dict) or not isinstance(data.get('value'),list): raise ValueError('Unexpected PSE data format')
        return [], len(data['value']), {'coverage':'data_only', 'note':'Market-data endpoint checked. This row is not a headline source; PSE news is monitored separately.'}
    elif kind == 'gdelt':
        data = json.loads(request(qurl(url, {'query':'(PGE OR Tauron OR Poland) sourcecountry:PL', 'mode':'artlist','format':'json','startdatetime':start.replace('-','')+'000000','maxrecords':250,'sort':'datedesc'})))
        entries = data.get('articles', [])
        limited = len(entries) >= 250
        records = [record(source,x.get('title',''),x.get('url',''),datetime.strptime(x['seendate'],'%Y%m%dT%H%M%SZ').isoformat(), lang='PL' if x.get('language')=='Polish' else 'EN',kind=kind,publisher=x.get('domain')) for x in entries if x.get('seendate')]
    elif kind == 'ted':
        payload = {'query':'buyer-country=POL AND publication-date>=' + start.replace('-',''),
                   'fields':['publication-number','notice-title','publication-date','buyer-name','classification-cpv'], 'page':1,'limit':250,'scope':'ALL','checkQuerySyntax':True}
        data = json.loads(request(url, payload))
        entries = data.get('notices', [])
        limited = len(entries) >= 250
        records = []
        for x in entries:
            title, lang = extract_language_titles(x.get('notice-title'))
            number = x.get('publication-number')
            if not number: continue
            date = x.get('publication-date','')
            if isinstance(date,list): date = date[0] if date else ''
            if re.fullmatch(r'\d{8}',str(date)): date=str(date)[:4]+'-'+str(date)[4:6]+'-'+str(date)[6:8]
            records.append(record(source,title,'https://ted.europa.eu/en/notice/-/detail/'+str(number),date,lang=lang,kind=kind))
    elif kind == 'bzp':
        # Endpoint returns a recent publication window. Its precise coverage is disclosed.
        entries = json.loads(request(qurl(url, {'PageSize':100,'PageNumber':1,'SortingColumnName':'PublicationDate','SortingDirection':'DESC'})))
        if not isinstance(entries,list): raise ValueError('Expected BZP notice array')
        limited = len(entries) >= 100
        records = [record(source,x.get('orderObject',''),'https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/'+str(x.get('objectId') or x.get('moIdentifier')),x.get('publicationDate'),x.get('organizationName',''),lang='PL',kind=kind) for x in entries if x.get('objectId') or x.get('moIdentifier')]
    else:
        raise ValueError('Unknown adapter: '+kind)
    return [x for x in records if x], len(entries), {'coverage':'limited_api_window' if limited else 'api_metadata', 'limited':limited,
        'note':'Latest API result window; not a full legal or procurement archive.'}


def fetch_source(source, start):
    items, reports = [], []
    for route in source['routes']:
        kind = route['kind']
        try:
            if kind == 'google':
                language = 'pl' if route['language'] == 'PL' else 'en-GB'
                end = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
                lookback = max(3, min(30, (datetime.now(timezone.utc).date() - datetime.fromisoformat(start).date()).days + 1))
                query = route['query'] + ' when:' + str(lookback) + 'd'
                url = qurl('https://news.google.com/rss/search', {'q':query,'hl':language,'gl':'PL','ceid':'PL:pl' if language=='pl' else 'GB:en'})
                found, total = parse_feed(source, request(url), route['language'], kind)
                note = {'coverage':'indexed_discovery','limited':total >= 100,'note':'Google News results; indexing delay and per-query result caps apply.'}
                # Fetch the latest two days separately if the initial result page hits its cap.
                if total >= 100:
                    recent = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
                    if recent > start:
                        q = route['query'] + ' when:3d'
                        recent_url = qurl('https://news.google.com/rss/search', {'q':q,'hl':language,'gl':'PL','ceid':'PL:pl' if language=='pl' else 'GB:en'})
                        extra, extra_count = parse_feed(source, request(recent_url), route['language'], kind)
                        found.extend(extra)
                        note['recentWindowEntries'] = extra_count
            elif kind == 'rss':
                found, total = parse_feed(source, request(route['url']), route['language'], kind)
                note = {'coverage':'publisher_feed','note':'Publisher feed recent window; no claim of a full publisher archive.'}
                url = route['url']
            else:
                found, total, note = fetch_api(source, route, start)
                url = route['url']
            found = [x for x in found if x['date'] >= start]
            items.extend(found)
            reports.append({'method':kind,'url':url,'language':route.get('language'), 'status':'success','entriesRead':total,'matched':len(found),**note})
        except Exception as error:
            reports.append({'method':kind,'url':route.get('url') or route.get('query'),'language':route.get('language'),'status':'error','error':str(error)[:250]})
    successful = [x for x in reports if x['status']=='success']
    status = 'success' if successful else 'error'
    direct = any(x['method'] not in ('google', 'pse_data') for x in successful)
    coverage = 'direct_and_indexed' if direct and any(x['method']=='google' for x in successful) else 'direct' if direct else 'indexed_discovery' if any(x['method']=='google' for x in successful) else 'data_only' if successful else 'unavailable'
    health = {'id':source['id'],'source':source['source'],'group':source['group'],'language':source['language'],
              'url':source['website'],'status':status,'coverage':coverage,'matched':len({x['id'] for x in items}),
              'latestPublicationDate':max((x['date'] for x in items),default=None),'routes':reports}
    if not successful:health['error']='; '.join(x.get('error','') for x in reports)
    return items, health


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def merge_records(previous, incoming):
    by_key = {}
    for item in previous + incoming:
        if not item.get('title') or not item.get('date'):continue
        title = item.get('title_pl') or item['title']
        key = (re.sub(r'\W+', ' ', title.casefold()).strip(),item['date'])
        old = by_key.get(key)
        if old:
            source_ids = sorted(set(old.get('sourceIds',[]) + item.get('sourceIds',[])))
            if (old.get('discoveryMethod') == 'google' and item.get('discoveryMethod') != 'google') or old.get('id') == item.get('id'):
                by_key[key] = item
            by_key[key]['sourceIds'] = source_ids
        else:by_key[key] = item
    return sorted(by_key.values(),key=lambda x:(x['date'],x['id']),reverse=True)


def normalise_languages(records, sources):
    lookup = {x['id']: x for x in sources}
    for item in records:
        if item.get('translated'):
            continue
        title = item.get('title_pl') or item['title']
        ids = item.get('sourceIds', [])
        strictly_polish = bool(ids) and all(lookup.get(i, {}).get('language') == 'PL' for i in ids)
        polish = strictly_polish or bool(re.search(r'[ąćęłńóśźż]|\b(?:oraz|sprawie|Polsce|budowa|podpisano|zawarcie|wyniki|zarząd|wykonawcę)\b',title,re.I))
        item['lang'] = 'pl' if polish else 'en'
        item['title_pl'] = title if polish else ''
        item['translationStatus'] = 'original_polish' if polish else 'not_required'
        if not polish and item.get('summary') == 'Polish original headline; English translation is not available.':
            item['summary'] = 'Indexed headline; open the publisher article for full details.'
    return records


def collect(fetcher=fetch_source):
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec='seconds')
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    sources = registry['sources']
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'updated':None,'signals':[]}
    previous_status = json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
    prior_health = {x.get('id'):x for x in previous_status.get('sources',[])}
    all_items, health = [], []
    def run(source):
        old = prior_health.get(source['id'], {})
        last = old.get('lastSuccessfulCheckAt')
        # First run includes 30 days; later runs overlap by two days to catch delayed indexing.
        since = (now.date() - timedelta(days=30)).isoformat()
        if last:
            since = max(since,(datetime.fromisoformat(last).date()-timedelta(days=2)).isoformat())
        items, state = fetcher(source, since)
        state['checkedAt'] = stamp
        state['lastSuccessfulCheckAt'] = stamp if state['status']=='success' else last
        state['windowStart'] = since
        return items, state
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        tasks = {pool.submit(run, source):source for source in sources}
        for task in concurrent.futures.as_completed(tasks):
            source = tasks[task]
            try: items, state = task.result()
            except Exception as error:
                items=[]
                state={'id':source['id'],'source':source['source'],'url':source['website'],'language':source['language'],'status':'error','coverage':'unavailable','matched':0,'error':str(error)[:250],'checkedAt':stamp,'routes':[]}
            all_items.extend(items);health.append(state)
            print(f"{state['status'].upper()} {state['source']}: {state['matched']} matches ({state['coverage']})",flush=True)
    successes = sum(x['status']=='success' for x in health)
    lookup = {x['id']: x for x in sources}
    retained = [item for item in previous.get('signals',[]) if relevant(lookup.get(next(iter(item.get('sourceIds',[])), ''), {'polandScoped':True}), item.get('title_pl') or item.get('title',''), item.get('summary',''))]
    records = normalise_languages(merge_records(retained,all_items), sources)
    previous_keys={(x.get('title_pl') or x.get('title'),x.get('date')) for x in previous.get('signals',[])}
    new_items = sum((x.get('title_pl') or x.get('title'),x['date']) not in previous_keys for x in records)
    cap=10000
    truncated=max(0,len(records)-cap)
    records=records[:cap]
    if successes:write_json(OUT, {'updated':stamp,'signals':records})
    status = {'checkedAt':stamp,'lastSuccessfulCollectionAt':stamp if successes else previous.get('updated'),
      'status':'success' if successes==len(sources) else 'partial' if successes else 'error',
      'successfulSources':successes,'totalSources':len(sources),'requestedWorkbookSources':registry['requestedRows'],
      'newItems':new_items,'retainedItems':len(records),'retentionDropped':truncated,'relevanceRemoved':len(previous.get('signals',[]))-len(retained),
      'latestPublicationDate':max((x['date'] for x in records),default=None),
      'polishOriginals':sum(x.get('lang')=='pl' and not x.get('translated') for x in records),
      'sources':sorted(health,key=lambda x:int(x['id'])),
      'scope':'All workbook rows are attempted. Indexed discovery, API windows and publisher feeds have different coverage; no guarantee of every article. Polish originals are retained and labelled when English translation is unavailable.'}
    write_json(STATUS,status)
    print(json.dumps({k:v for k,v in status.items() if k!='sources'},ensure_ascii=False))
    return 0 if successes else 1


if __name__ == '__main__':sys.exit(collect())
