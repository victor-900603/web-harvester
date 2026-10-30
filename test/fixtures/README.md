# Offline fixtures

`test/test_integration_offline.py` runs the full pipeline against these files
instead of the network: config loading, list parsing, article parsing,
robots.txt handling and storage are all exercised for real.

Every file is a trimmed copy of a live response captured on 2026-10-30.

| File | Captured from |
| --- | --- |
| `cna/list_page.json` | `POST https://www.cna.com.tw/cna2018api/api/WNewsList` (page 2) |
| `cna/article.html` | one article linked from that response |
| `setn/list_page.html` | `GET https://www.setn.com/news/getlastestnews/1/1` |
| `setn/article.html` | one article linked from that response |

Trimming only removes material the crawler never looks at:

- `<script>`, `<style>`, `<noscript>`, `<iframe>` and `<link>` are dropped.
- `<head>` is kept as-is so meta tags stay realistic.
- Only the containers referenced by the site config are kept, plus the three
  first paragraphs of the article body. Paragraphs that hold a parsed element
  (such as the author link) are always kept.

Two deliberate edits make the fixtures useful:

- `cna/list_page.json` keeps two regular articles plus one `netzero.cna.com.tw`
  entry, so the `exclude_patterns` rule is genuinely exercised.
- `setn/list_page.html` keeps four items that link to `www.setn.com`; items
  pointing at `star.setn.com` are removed because the site config targets the
  canonical host.

`capture_fixtures.py` refreshes these files. It talks to the live sites, so run
it manually when a site changes its markup:

```bash
python test/fixtures/capture_fixtures.py
```
