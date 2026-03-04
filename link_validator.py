#!/usr/bin/env python3
"""
CMACED Startup Intelligence Dashboard — link_validator.py
Superior University × ID92

Runs after scraper.py:
1. Re-validates every application_link (HTTP 200 check)
2. Rejects news/RSS/redirect links
3. Archives entries with passed deadlines
4. Deduplicates by ID
5. Recalculates status for all entries
6. Writes detailed log
"""

import json
import logging
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import re

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
OPP_FILE = BASE_DIR / 'opportunities.json'
ARCH_FILE= BASE_DIR / 'archive.json'
LOG_FILE = BASE_DIR / 'scraper' / 'validation.log'

TODAY    = datetime.utcnow().date()
TIMEOUT  = 12
MAX_WORKERS = 5

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (compatible; CMACED-Validator/2.0; '
        '+https://superior.edu.pk/cmaced)'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Bad URL patterns — any link matching these is rejected
BAD_PATTERNS = re.compile(
    r'news\.google\.com|google\.com/url\?|bing\.com/news|'
    r'[?&](utm_|fbclid|gclid)|feedproxy\.google|'
    r'/rss|rss\.|\.rss|/feed|feed\.|\.feed|/amp/|amp\.',
    re.IGNORECASE
)


# ── Helpers ────────────────────────────────────────────────────
def load_json(path: Path) -> list:
    if path.exists():
        try:
            d = json.loads(path.read_text('utf-8'))
            return d if isinstance(d, list) else []
        except Exception as e:
            log.error(f'Load error {path}: {e}')
    return []


def save_json(path: Path, data: list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), 'utf-8')
    log.info(f'Saved {len(data)} entries → {path.name}')


def clean_url(url: str) -> str:
    if not url:
        return ''
    try:
        p = urlparse(url)
        bad = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content',
               'fbclid','gclid','ref','referrer','source','mc_cid','mc_eid'}
        qs = {k: v for k, v in parse_qs(p.query, keep_blank_values=True).items()
              if k.lower() not in bad}
        return urlunparse(p._replace(query=urlencode(qs, doseq=True), fragment=''))
    except Exception:
        return url


def parse_deadline(s: str):
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def compute_status(entry: dict) -> str:
    dl = parse_deadline(entry.get('deadline', ''))
    if not dl:
        return 'Open'
    if dl < TODAY:
        return 'Closed'
    if (dl - TODAY).days <= 7:
        return 'Closing Soon'
    try:
        added = date.fromisoformat((entry.get('date_added', ''))[:10])
        if (TODAY - added).days <= 2:
            return 'New'
    except Exception:
        pass
    return 'Open'


# ── Link Checking ──────────────────────────────────────────────
def check_link(url: str) -> tuple[bool, str]:
    """
    Returns (is_valid: bool, reason: str).
    Performs HEAD then GET fallback.
    """
    if not url:
        return False, 'empty URL'
    if not url.startswith('http'):
        return False, 'not HTTP'
    if BAD_PATTERNS.search(url):
        return False, 'bad URL pattern (news/RSS/redirect)'

    url = clean_url(url)

    try:
        resp = requests.head(
            url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
        final = resp.url

        # Reject if redirected to a bad domain
        if BAD_PATTERNS.search(final):
            return False, f'redirected to bad URL: {final}'

        if resp.status_code == 200:
            return True, 'HTTP 200'

        # HEAD rejected — try GET
        if resp.status_code in (405, 406, 403):
            resp2 = requests.get(
                url, headers=HEADERS, timeout=TIMEOUT,
                allow_redirects=True, stream=True
            )
            resp2.close()
            if BAD_PATTERNS.search(resp2.url):
                return False, f'GET redirected to bad URL: {resp2.url}'
            if resp2.status_code == 200:
                return True, 'HTTP 200 (GET fallback)'
            return False, f'HTTP {resp2.status_code} (GET)'

        return False, f'HTTP {resp.status_code}'

    except requests.exceptions.SSLError:
        return False, 'SSL error'
    except requests.exceptions.ConnectionError:
        return False, 'connection error'
    except requests.exceptions.Timeout:
        return False, f'timeout ({TIMEOUT}s)'
    except Exception as e:
        return False, f'error: {e}'


def validate_entry(entry: dict) -> dict:
    result = entry.copy()
    url = entry.get('application_link', '')
    ok, reason = check_link(url)
    result['_valid']   = ok
    result['_reason']  = reason
    dl = parse_deadline(entry.get('deadline', ''))
    result['_expired'] = bool(dl and dl < TODAY)
    result['status']   = compute_status(entry)
    if ok:
        log.info(f"  ✓ [{entry.get('id','')}] {reason}")
    else:
        log.warning(f"  ✗ [{entry.get('id','')}] {reason} — {url}")
    return result


# ── Deduplication ──────────────────────────────────────────────
def dedup(entries: list) -> list:
    seen = {}
    for e in entries:
        eid = e.get('id', '')
        if eid not in seen:
            seen[eid] = e
        else:
            # Keep newer date_added
            if e.get('date_added', '') > seen[eid].get('date_added', ''):
                seen[eid] = e
    return list(seen.values())


# ── Main ───────────────────────────────────────────────────────
def run():
    opps    = load_json(OPP_FILE)
    archive = load_json(ARCH_FILE)

    if not opps:
        log.warning('No opportunities to validate.')
        return

    log.info(f'Validating {len(opps)} opportunities with {MAX_WORKERS} workers…')

    validated = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(validate_entry, e): e for e in opps}
        for fut in as_completed(futures):
            try:
                validated.append(fut.result())
            except Exception as err:
                e = futures[fut]
                log.error(f"Worker error [{e.get('id','?')}]: {err}")
                e2 = e.copy()
                e2['_valid'] = False
                e2['_expired'] = False
                e2['_reason'] = f'exception: {err}'
                e2['status'] = 'Open'
                validated.append(e2)

    active  = []
    to_arch = []
    log_lines = [f'=== Validation Run: {datetime.utcnow().isoformat()} ===']

    for e in validated:
        clean = {k: v for k, v in e.items() if not k.startswith('_')}
        if e['_expired']:
            clean['status'] = 'Closed'
            to_arch.append(clean)
            log_lines.append(f'ARCHIVED  | {e["id"]} | deadline {e.get("deadline","")}')
        elif not e['_valid']:
            log_lines.append(f'REMOVED   | {e["id"]} | {e["_reason"]} | {e.get("application_link","")}')
        else:
            active.append(clean)

    # Merge into archive (no duplicates)
    arch_ids = {a['id'] for a in archive}
    for entry in to_arch:
        if entry['id'] not in arch_ids:
            archive.append(entry)

    active  = dedup(active)
    archive = dedup(archive)

    save_json(OPP_FILE, active)
    save_json(ARCH_FILE, archive)

    # Summary
    removed  = sum(1 for l in log_lines if l.startswith('REMOVED'))
    archived = sum(1 for l in log_lines if l.startswith('ARCHIVED'))

    log.info(f"""
{'='*55}
Validation Summary — {TODAY}
  Active opportunities : {len(active)}
  Archived (expired)   : {archived}
  Removed (broken)     : {removed}
  Archive total        : {len(archive)}
{'='*55}""")

    # Write log
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write('\n'.join(log_lines) + '\n')
        f.write(f'SUMMARY   | active={len(active)} archived={archived} removed={removed}\n\n')

    log.info('Validation complete.')


if __name__ == '__main__':
    run()
