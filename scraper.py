#!/usr/bin/env python3
"""
CMACED Startup Intelligence Dashboard — scraper.py
Superior University × ID92

Scrapes only official program pages.
Pre-validates every link before storing.
Rejects broken, redirected, news, or RSS links.
"""

import json
import re
import time
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
OPP_FILE = BASE_DIR / 'opportunities.json'
ARCH_FILE= BASE_DIR / 'archive.json'
TODAY    = datetime.utcnow().date()

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        'CMACED-Bot/2.0 (https://superior.edu.pk; institutional research)'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}
TIMEOUT = 15

# Patterns that indicate a link is NOT an official program page
BAD_LINK_PATTERNS = [
    r'news\.google\.com',
    r'google\.com/url',
    r'bing\.com/news',
    r'/rss',
    r'rss\.', r'\.rss',
    r'feed\.', r'\.feed',
    r'redirect\.',
    r'[?&](utm_|ref=|tracking|source=news)',
    r'feedproxy\.google',
    r'amp\.', r'/amp/',
    r'medium\.com/feed',
]
BAD_LINK_RE = re.compile('|'.join(BAD_LINK_PATTERNS), re.IGNORECASE)

# Sources registry
SOURCES = [
    # ── Pakistan Government ────────────────────────────────────────────────
    {
        'id': 'ignite-startup-fund',
        'name': 'Ignite Startup Fund',
        'organization': 'Ignite National Technology Fund',
        'type': 'grant',
        'country': 'Pakistan',
        'region': 'national',
        'prize': 'PKR 5–25 million',
        'requirements': 'Early-stage tech startups registered in Pakistan. Working prototype required.',
        'page_url': 'https://ignite.org.pk/programs/',
        'apply_url': 'https://ignite.org.pk/programs/',
        'source_url': 'https://ignite.org.pk',
    },
    {
        'id': 'plan9-incubator',
        'name': 'Plan9 Incubation Program',
        'organization': 'PITB – Punjab Information Technology Board',
        'type': 'accelerator',
        'country': 'Pakistan',
        'region': 'national',
        'prize': 'Office space + PKR 1M seed',
        'requirements': 'Tech-based startup teams from Punjab. Pre-revenue or early revenue stage.',
        'page_url': 'https://plan9.pitb.gov.pk',
        'apply_url': 'https://plan9.pitb.gov.pk',
        'source_url': 'https://plan9.pitb.gov.pk',
    },
    {
        'id': 'nic-lahore',
        'name': 'National Incubation Center Lahore',
        'organization': 'NIC Lahore / STZA',
        'type': 'accelerator',
        'country': 'Pakistan',
        'region': 'national',
        'prize': 'USD 10,000 + mentorship',
        'requirements': 'Pakistani founders. Tech/innovation focused. Presentation required.',
        'page_url': 'https://niclahore.com',
        'apply_url': 'https://niclahore.com',
        'source_url': 'https://niclahore.com',
    },
    {
        'id': 'hec-innovation-fund',
        'name': 'HEC Innovation & Research Fund',
        'organization': 'Higher Education Commission Pakistan',
        'type': 'grant',
        'country': 'Pakistan',
        'region': 'national',
        'prize': 'PKR 2–10 million',
        'requirements': 'University-affiliated researchers and student entrepreneurs in Pakistan.',
        'page_url': 'https://hec.gov.pk/english/services/faculty/NRPU/Pages/Default.aspx',
        'apply_url': 'https://hec.gov.pk/english/services/faculty/NRPU/Pages/Default.aspx',
        'source_url': 'https://hec.gov.pk',
    },
    {
        'id': 'pseb-ites-support',
        'name': 'PSEB IT Export Startup Support',
        'organization': 'Pakistan Software Export Board',
        'type': 'grant',
        'country': 'Pakistan',
        'region': 'national',
        'prize': 'PKR 3 million + export facilitation',
        'requirements': 'IT/software companies targeting export markets. Must be PSEB registered.',
        'page_url': 'https://pseb.org.pk',
        'apply_url': 'https://pseb.org.pk',
        'source_url': 'https://pseb.org.pk',
    },
    # ── Pakistan Universities ──────────────────────────────────────────────
    {
        'id': 'cmaced-startup-grant',
        'name': 'CMACED Internal Startup Grant',
        'organization': 'CMACED – Superior University',
        'type': 'grant',
        'country': 'Pakistan',
        'region': 'national',
        'prize': 'PKR 500,000',
        'requirements': 'Currently enrolled Superior University students. Prototype required.',
        'page_url': 'https://superior.edu.pk',
        'apply_url': 'https://superior.edu.pk',
        'source_url': 'https://superior.edu.pk',
    },
    {
        'id': 'lums-entrepreneurship',
        'name': 'LUMS Centre for Entrepreneurship Program',
        'organization': 'LUMS – Lahore University of Management Sciences',
        'type': 'accelerator',
        'country': 'Pakistan',
        'region': 'national',
        'prize': 'Mentorship + USD 5,000 seed',
        'requirements': 'Open to all Pakistani university graduates and students.',
        'page_url': 'https://lums.edu.pk/centre-entrepreneurship',
        'apply_url': 'https://lums.edu.pk/centre-entrepreneurship',
        'source_url': 'https://lums.edu.pk',
    },
    # ── International ──────────────────────────────────────────────────────
    {
        'id': 'yc-accelerator',
        'name': 'Y Combinator Accelerator',
        'organization': 'Y Combinator',
        'type': 'accelerator',
        'country': 'USA',
        'region': 'international',
        'prize': 'USD 500,000',
        'requirements': 'Any stage, any country. Online application open. Equity-based.',
        'page_url': 'https://www.ycombinator.com/apply',
        'apply_url': 'https://www.ycombinator.com/apply',
        'source_url': 'https://www.ycombinator.com',
    },
    {
        'id': 'hult-prize',
        'name': 'Hult Prize Global Competition',
        'organization': 'Hult Prize Foundation',
        'type': 'competition',
        'country': 'Global',
        'region': 'international',
        'prize': 'USD 1,000,000',
        'requirements': 'University student teams. Social impact focus. Virtual worldwide.',
        'page_url': 'https://www.hultprize.org',
        'apply_url': 'https://www.hultprize.org',
        'source_url': 'https://www.hultprize.org',
    },
    {
        'id': 'mit-solve-challenge',
        'name': 'MIT Solve Global Challenge',
        'organization': 'MIT Solve',
        'type': 'competition',
        'country': 'Global',
        'region': 'international',
        'prize': 'USD 10,000–150,000',
        'requirements': 'Social entrepreneurs worldwide. Online application accepted from Pakistan.',
        'page_url': 'https://solve.mit.edu',
        'apply_url': 'https://solve.mit.edu',
        'source_url': 'https://solve.mit.edu',
    },
    {
        'id': 'google-startups-accelerator',
        'name': 'Google for Startups Accelerator',
        'organization': 'Google',
        'type': 'accelerator',
        'country': 'Global',
        'region': 'international',
        'prize': 'USD 100,000 in Cloud credits (equity-free)',
        'requirements': 'Series A or earlier. AI/ML focused preferred. Virtual available.',
        'page_url': 'https://startup.google.com/programs/accelerator/',
        'apply_url': 'https://startup.google.com/programs/accelerator/',
        'source_url': 'https://startup.google.com',
    },
    {
        'id': 'msft-founders-hub',
        'name': 'Microsoft for Startups Founders Hub',
        'organization': 'Microsoft',
        'type': 'grant',
        'country': 'Global',
        'region': 'international',
        'prize': 'USD 150,000 in Azure credits',
        'requirements': 'Pre-seed to Series A. No equity required. Pakistan-based welcome.',
        'page_url': 'https://www.microsoft.com/en-us/startups',
        'apply_url': 'https://www.microsoft.com/en-us/startups',
        'source_url': 'https://www.microsoft.com/en-us/startups',
    },
    {
        'id': 'seedstars-world',
        'name': 'Seedstars World Competition',
        'organization': 'Seedstars World',
        'type': 'competition',
        'country': 'Global',
        'region': 'international',
        'prize': 'USD 500,000 investment',
        'requirements': 'Early-stage tech startups. Local qualifying rounds then global finals.',
        'page_url': 'https://www.seedstars.com/programs/',
        'apply_url': 'https://www.seedstars.com/programs/',
        'source_url': 'https://www.seedstars.com',
    },
    {
        'id': 'masschallenge-accelerator',
        'name': 'MassChallenge Global Accelerator',
        'organization': 'MassChallenge',
        'type': 'accelerator',
        'country': 'Global',
        'region': 'international',
        'prize': 'USD 250,000 equity-free',
        'requirements': 'No equity taken. Open to international founders including Pakistan.',
        'page_url': 'https://masschallenge.org',
        'apply_url': 'https://masschallenge.org',
        'source_url': 'https://masschallenge.org',
    },
    {
        'id': 'devpost-hackathons',
        'name': 'Devpost Global Hackathons',
        'organization': 'Devpost',
        'type': 'hackathon',
        'country': 'Global',
        'region': 'international',
        'prize': 'Varies per hackathon',
        'requirements': 'Virtual. Open to all nationalities. Individual or team submission.',
        'page_url': 'https://devpost.com/hackathons',
        'apply_url': 'https://devpost.com/hackathons',
        'source_url': 'https://devpost.com',
    },
    {
        'id': '500-global',
        'name': '500 Global Accelerator',
        'organization': '500 Global',
        'type': 'accelerator',
        'country': 'Global',
        'region': 'international',
        'prize': 'USD 150,000 investment',
        'requirements': 'Early-stage startups. Open to Pakistani founders. Online application.',
        'page_url': 'https://500.co/accelerators',
        'apply_url': 'https://500.co/accelerators',
        'source_url': 'https://500.co',
    },
]


# ── Link Validation ────────────────────────────────────────────
def is_bad_url(url: str) -> bool:
    """Return True if URL matches known bad patterns."""
    if not url:
        return True
    return bool(BAD_LINK_RE.search(url))


def clean_url(url: str) -> str:
    """Remove tracking parameters and clean URL."""
    if not url:
        return ''
    try:
        parsed = urlparse(url)
        # Remove known tracking params
        bad_params = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content',
                      'ref','referrer','source','tracking','fbclid','gclid','mc_cid','mc_eid'}
        qs = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {k: v for k, v in qs.items() if k.lower() not in bad_params}
        new_query = urlencode(cleaned, doseq=True)
        return urlunparse(parsed._replace(query=new_query, fragment=''))
    except Exception:
        return url


def validate_link(url: str, timeout: int = TIMEOUT) -> bool:
    """
    Return True if URL:
    - Is not a bad/redirected/news/RSS link
    - Returns HTTP 200 from official domain
    """
    if is_bad_url(url):
        log.warning(f'  ✗ Bad URL pattern: {url}')
        return False

    url = clean_url(url)
    if not url.startswith('http'):
        return False

    try:
        resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)

        # After redirects, check final URL is not a bad domain
        final_url = resp.url
        if is_bad_url(final_url):
            log.warning(f'  ✗ Redirected to bad URL: {final_url}')
            return False

        if resp.status_code == 200:
            return True

        # Some servers reject HEAD — try GET
        if resp.status_code in (405, 406, 403):
            resp2 = requests.get(url, headers=HEADERS, timeout=timeout,
                                 allow_redirects=True, stream=True)
            resp2.close()
            if is_bad_url(resp2.url):
                return False
            return resp2.status_code == 200

        log.warning(f'  ✗ HTTP {resp.status_code}: {url}')
        return False

    except requests.exceptions.SSLError:
        log.warning(f'  ✗ SSL error: {url}')
        return False
    except requests.exceptions.ConnectionError:
        log.warning(f'  ✗ Connection error: {url}')
        return False
    except requests.exceptions.Timeout:
        log.warning(f'  ✗ Timeout: {url}')
        return False
    except Exception as e:
        log.warning(f'  ✗ Error {url}: {e}')
        return False


# ── Scraping ───────────────────────────────────────────────────
def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        log.debug(f'Fetch failed {url}: {e}')
    return None


DATE_PATTERNS = [
    (r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b', '%d %B %Y'),
    (r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b', '%B %d %Y'),
    (r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b', '%d %b %Y'),
    (r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4})\b', '%b %d %Y'),
    (r'\b(\d{4}-\d{2}-\d{2})\b', '%Y-%m-%d'),
    (r'\b(\d{2}/\d{2}/\d{4})\b', '%d/%m/%Y'),
]
DEADLINE_KEYWORDS = [
    'deadline', 'apply by', 'last date', 'closes on', 'due date',
    'submission deadline', 'application deadline', 'close on', 'closing date',
]


def extract_deadline(soup: BeautifulSoup) -> str:
    if not soup:
        return ''
    text = soup.get_text(' ', strip=True)
    text_lower = text.lower()

    for kw in DEADLINE_KEYWORDS:
        idx = text_lower.find(kw)
        if idx == -1:
            continue
        snippet = text[idx:idx+180]
        for pattern, fmt in DATE_PATTERNS:
            m = re.search(pattern, snippet, re.IGNORECASE)
            if m:
                raw = m.group(1).strip().replace(',', '')
                for f in [fmt, '%B %d %Y', '%b %d %Y', '%d %B %Y', '%d %b %Y', '%Y-%m-%d', '%d/%m/%Y']:
                    try:
                        d = datetime.strptime(raw, f).date()
                        # Only accept future dates or up to 30 days past
                        if d >= TODAY - timedelta(days=30):
                            return d.isoformat()
                    except ValueError:
                        pass
    return ''


def find_apply_link_on_page(soup: BeautifulSoup, base_url: str, org_domain: str) -> str:
    """Find a better apply link on the page, must be same domain."""
    if not soup:
        return ''
    kws = ['apply now', 'apply here', 'apply online', 'start application', 'register now', 'submit application']
    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True).lower()
        href = a['href']
        if not href or href.startswith('#') or href.startswith('mailto:'):
            continue
        if any(kw in text for kw in kws):
            full = urljoin(base_url, href)
            parsed = urlparse(full)
            # Must be on same or org domain
            if org_domain in parsed.netloc and full.startswith('http'):
                return full
    return ''


# ── Main ───────────────────────────────────────────────────────
def load_json(path: Path) -> list:
    if path.exists():
        try:
            data = json.loads(path.read_text('utf-8'))
            return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


def save_json(path: Path, data: list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), 'utf-8')
    log.info(f'Saved {len(data)} entries → {path.name}')


def run():
    existing = {o['id']: o for o in load_json(OPP_FILE)}
    archive  = {o['id']: o for o in load_json(ARCH_FILE)}

    valid_entries = []
    discarded = 0

    for src in SOURCES:
        log.info(f"\n→ Processing: {src['name']}")

        apply_url  = src.get('apply_url', '')
        page_url   = src.get('page_url', apply_url)
        source_url = src.get('source_url', page_url)

        # Step 1: Pre-validate the apply link
        log.info(f"  Validating apply link: {apply_url}")
        link_ok = validate_link(apply_url)

        if not link_ok:
            # Step 2: Try to find apply link from the source page
            log.warning(f"  Apply link failed. Trying source page: {source_url}")
            soup = fetch_page(source_url)
            org_domain = urlparse(source_url).netloc.replace('www.', '')
            if soup:
                found = find_apply_link_on_page(soup, source_url, org_domain)
                if found and validate_link(found):
                    apply_url = found
                    link_ok = True
                    log.info(f"  ✓ Found fallback apply link: {apply_url}")

        if not link_ok:
            log.warning(f"  ✗ Discarding — no valid apply link for: {src['name']}")
            discarded += 1
            time.sleep(0.5)
            continue

        # Step 3: Scrape for deadline
        soup = fetch_page(page_url)
        deadline = extract_deadline(soup) if soup else ''
        if deadline:
            log.info(f"  → Deadline extracted: {deadline}")

        # Step 4: Build entry
        old = existing.get(src['id'])
        entry = {
            'id':               src['id'],
            'name':             src['name'],
            'organization':     src['organization'],
            'type':             src['type'],
            'country':          src['country'],
            'region':           src['region'],
            'deadline':         deadline or (old.get('deadline', '') if old else ''),
            'prize':            src.get('prize', ''),
            'requirements':     src.get('requirements', ''),
            'application_link': clean_url(apply_url),
            'source':           source_url,
            'date_added':       old.get('date_added', TODAY.isoformat()) if old else TODAY.isoformat(),
            'status':           'Open',
        }
        valid_entries.append(entry)
        log.info(f"  ✓ Added: {src['name']}")
        time.sleep(1.2)  # polite crawling

    log.info(f'\nScrape summary: {len(valid_entries)} valid, {discarded} discarded')
    save_json(OPP_FILE, valid_entries)
    save_json(ARCH_FILE, list(archive.values()))
    log.info('Done.')


if __name__ == '__main__':
    run()
