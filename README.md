# Poland Power Pulse — scheduled feed updates

The dashboard is published at https://neelamgulati7788.github.io/poland-power-pulse-v34/.

The workflow `.github/workflows/update-feed.yml` collects configured English RSS/Atom feeds at minutes 7 and 37 each hour (GitHub may delay scheduled runs), saves the JSON and source-health report, then deploys the dashboard and data together. It also runs after relevant code changes or a manual **Run workflow**.

GitHub **Settings → Pages → Source** must be **GitHub Actions**. No API key is required.

## Scope and status

- `scripts/feed_fetcher.py` filters seven publisher feeds for Polish power-sector keywords, retaining at most 400 collected records alongside the HTML's embedded curated history.
- Feeds: CEEnergyNews, ESS News, pv magazine, Notes From Poland, Baltic Wind, Renewables Now and World Nuclear News. This is limited English-language coverage, not comprehensive monitoring of all sources listed in the dashboard. Blocked, malformed or unavailable sources are reported explicitly; they are not bypassed.
- Feed windows may contain no relevant new articles. A successful check does not imply a newly published article.
- Automated items are tagged RSS. They are source headlines/excerpts with keyword classification, not translated Polish articles or analyst-reviewed material-change assessments. The existing dashboard also displays these classified items in its Signal Monitor.
- `data/signals.json` contains collected records and the last successful collection timestamp. Total source failure preserves the previous feed.
- `data/collection-status.json` records each attempt, per-source failures, matched counts, latest publication date, and overall success/partial/error.
- The header reports partial results, stale data (over 75 minutes), missing feeds and failed collection. Hover over it for per-source details. The displayed date no longer advances just because the page was opened.
- The browser reloads published JSON every 30 minutes while open. Reopening the page loads the newest published batch immediately.
- Initial RSS feeds provide only their recent window; they do not guarantee all news since the embedded snapshot. A separate historical backfill or broader primary-source collection would be additional work.

## Verification

Run `python -m unittest discover -s tests`, then `python scripts/feed_fetcher.py`. The collection job fails if every source fails, and the deployment still publishes the failure report with the retained data. GitHub Actions logs and step summaries show the actual collection outcome.

`data/headlines.json` supplies optional headline overrides. `newsletter_assets/logo.png` remains optional and was not included in the uploaded ZIP.
