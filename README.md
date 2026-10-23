# Poland Power Pulse — English and Polish source monitoring

Dashboard: https://neelamgulati7788.github.io/poland-power-pulse-v34/

## Source register

`data/sources.json` registers every one of the 71 rows in the supplied `sources.xlsx`, plus the existing Baltic Wind source. Each row retains its name, group, language, website and requested access method. Concrete collectors replace placeholder endpoints and empty `()` search queries. Mixed-language sources have English and Polish discovery routes. The combined law-firm row covers Dentons, CMS and SSW.

The **Sources** panel reports each source's check status, route, latest matching publication, count, errors and limits. A successful index query is labelled **indexed discovery**, not a direct publisher check. CEEnergyNews and Renewables Now use public Google News discovery when their direct feeds are unavailable. Google links are labelled as indexed discovery, not misrepresented as verified full-text publisher retrievals.

## Refresh and limits

The GitHub workflow collects and deploys at minutes 7 and 37 each hour, after relevant edits, and on manual dispatch. GitHub may delay scheduled starts. The browser reloads published data every 30 minutes while open. A full refresh loads the newest deployed batch immediately.

Initial discovery uses a 30-day window, with an extra recent query where Google returns 100 results. Later runs overlap by at least two days. Publisher RSS has its own recent window; search indexing can lag or omit stories. TED and BZP adapters expose bounded recent result windows. ELI and Sejm metadata are filtered for energy relevance. The PSE market-data row is a health check, not a news feed; the separate PSE news row monitors announcements. GDELT may be unavailable and is reported explicitly.

**This is not a guarantee of every article or exhaustive procurement/legal coverage.** Every source row is attempted; caps, unavailable endpoints and coverage methods are visible rather than treated as complete access. Original publication dates and collection timestamps are kept separately. Previous records survive total collection outages, and retained history is capped at 10,000 collected records with any truncation reported.

## Language and evidence

English and Polish headlines are published. New Polish originals are labelled **PL original · translation unavailable** when no English translation is available; they are not dropped or falsely described as translated. Curated English translations remain intact. Unreviewed automatic records carry **Indexed** or **Collected** labels. They are headlines/excerpts with keyword classification, not analyst-reviewed material-change assessments. Google index summaries are not represented as article summaries. No translation subscription or API key has been configured.

Headlines are filtered using Polish and English energy vocabulary, company names and geography. Recruitment and routine MAR personal-transaction announcements are excluded. Exact title/date duplicates prefer direct feeds, and the UI also merges near-duplicate headlines. The news view is paginated with all retained articles still searchable.

## Files and checks

- `index.html`: dashboard and embedded curated history.
- `data/sources.json`: editable, versioned source register.
- `data/signals.json`: collected items and last successful collection timestamp.
- `data/collection-status.json`: complete per-source and per-route audit.
- `data/headlines.json`: optional verified-headline overrides; embedded overrides still work if absent.
- `scripts/feed_fetcher.py`: standard-library-only source collector.
- `tests/test_feed_fetcher.py`: language, provenance, relevance, merge and outage tests.
- `.github/workflows/update-feed.yml`: tests, collection, commit and atomic Pages deployment.

Run `python -m unittest discover -s tests` and `python scripts/feed_fetcher.py` from the repository root. Pages publishing source must be **GitHub Actions**.
