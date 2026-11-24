# Scrapers

Supported institutions:

- Cal Poly Pomona
- De Anza College (prototype)

## Workflow

Run URL discovery first, then run the institution’s `scrape_catalog.py`.

```text
python scrapers/CalPolyPomona/get_urls.py
python scrapers/DeAnzaCollege/get_urls.py
python scrapers/DeAnzaCollege/scrape_catalog.py --all-programs --all-departments --force
```

All commands support `-h` / `--help`.

## Flag overview

| Flag | Scrapers | Purpose |
| --- | --- | --- |
| `--program PROGRAM` | Both catalog scrapers | Scrape one program; repeatable. |
| `--department DEPARTMENT` | Both catalog scrapers | Scrape one department; repeatable. For De Anza, this means a subject department. |
| `--all-programs` | Both catalog scrapers | Scrape every discovered program. |
| `--all-departments` | Both catalog scrapers | Scrape every discovered department. |
| `--force` | Both catalog scrapers; CPP URL discovery | Rebuild existing selected outputs instead of skipping or merging them. |
| `--only PROGRAM` | CPP catalog scraper | Backwards-compatible alias for `--program`. |
| `--html FILE` | De Anza URL discovery | Parse a saved Course Listings HTML file offline. |
| `--degree-html FILE` | De Anza URL discovery | Parse a saved Degree and Certificate Listings HTML file offline. |
| `-h`, `--help` | All commands | Show available options. |

Flags may be combined. With no selector, catalog scrapers process all available
programs and departments. `--force` is recommended when rerunning after parser
changes.

## Common examples

```text
python scrapers/CalPolyPomona/scrape_catalog.py --program "Computer Science, B.S." --force
python scrapers/DeAnzaCollege/scrape_catalog.py --department CIS --force
python scrapers/DeAnzaCollege/scrape_catalog.py --all-programs --force
python scrapers/DeAnzaCollege/get_urls.py --degree-html saved-degree-listings.html
```
