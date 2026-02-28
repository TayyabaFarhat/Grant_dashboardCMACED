"""
LaunchPad Intelligence — Main Scraper
Scrapes startup opportunities from multiple public sources.
Runs via GitHub Actions daily.
"""

import json
import hashlib
import logging
import re
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---- Setup ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 15
OUTPUT_FILE = Path(__file__).parent.parent / "opportunities.json"


# ---- Utility ----

def safe_get(url, **kwargs):
    try:
        resp = SESSION.get(url, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except Exception as e:
        log.warning(f"Failed to fetch {url}: {e}")
        return None


def make_id(name, org):
    key = f"{name}{org}".lower()
    return hashlib.md5(key.encode()).hexdigest()[:8]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_opp(opp):
    """Ensure all required fields exist."""
    defaults = {
        "id": make_id(opp.get("name", ""), opp.get("organization", "")),
        "name": "",
        "organization": "",
        "category": "",
        "type": "competition",
        "country": "Global",
        "deadline": "",
        "prize": "Varies",
        "link": "",
        "source": "",
        "date_added": now_iso(),
        "status": "open",
        "description": "",
        "tags": [],
    }
    for k, v in defaults.items():
        opp.setdefault(k, v)
    for field in ["name", "organization", "country", "prize", "description"]:
        opp[field] = str(opp[field]).strip()
    return opp


# ---- Source: Devpost RSS ----

def scrape_devpost():
    log.info("Scraping Devpost RSS...")
    opps = []
    url = "https://devpost.com/hackathons.rss"
    resp = safe_get(url)
    if not resp:
        return opps

    soup = BeautifulSoup(resp.text, "xml")
    items = soup.find_all("item")[:20]

    for item in items:
        title = item.find("title")
        link = item.find("link")
        desc = item.find("description")

        if not title or not link:
            continue

        name = title.get_text(strip=True)
        url_val = link.get_text(strip=True)
        description = BeautifulSoup(
            desc.get_text(strip=True) if desc else "", "html.parser"
        ).get_text()[:250]

        opps.append(
            normalize_opp(
                {
                    "name": name,
                    "organization": "Devpost",
                    "category": "Hackathon",
                    "type": "hackathon",
                    "country": "Global",
                    "link": url_val,
                    "source": "devpost.com",
                    "description": description,
                    "tags": ["virtual", "online"],
                }
            )
        )
        time.sleep(0.2)

    log.info(f"Devpost: {len(opps)} opportunities")
    return opps


# ---- Source: Challenge.gov RSS ----

def scrape_challenge_gov():
    log.info("Scraping Challenge.gov RSS...")
    opps = []
    url = "https://www.challenge.gov/api/challenges.json"
    resp = safe_get(url)
    if not resp:
        return opps

    try:
        data = resp.json()
        challenges = data.get("results", [])[:15]
        for ch in challenges:
            name = ch.get("title", "")
            org = ch.get("agency_name", "US Government")
            prize = f"${ch.get('total_prize_offered_amount', 0):,.0f}" if ch.get(
                "total_prize_offered_amount"
            ) else "Varies"
            deadline = ch.get("end_date", "")
            link = ch.get("url", f"https://www.challenge.gov/challenge/{ch.get('id', '')}")
            desc = ch.get("brief_description", "")[:250]

            opps.append(
                normalize_opp(
                    {
                        "name": name,
                        "organization": org,
                        "category": "Grant",
                        "type": "grant",
                        "country": "United States",
                        "deadline": deadline[:10] if deadline else "",
                        "prize": prize,
                        "link": link,
                        "source": "challenge.gov",
                        "description": desc,
                        "tags": ["federal", "us-government"],
                    }
                )
            )
    except Exception as e:
        log.warning(f"Challenge.gov parse error: {e}")

    log.info(f"Challenge.gov: {len(opps)} opportunities")
    return opps


# ---- Source: F6S via public search ----

def scrape_f6s():
    log.info("Scraping F6S...")
    opps = []
    url = "https://www.f6s.com/programs"
    resp = safe_get(url)
    if not resp:
        return opps

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select(".program-card, .program-item, article.program")[:15]

    for card in cards:
        title_el = card.select_one("h2, h3, .program-title, .title")
        link_el = card.select_one("a[href]")
        org_el = card.select_one(".org-name, .company, .organizer")
        desc_el = card.select_one(".description, p")

        if not title_el or not link_el:
            continue

        name = title_el.get_text(strip=True)
        href = link_el.get("href", "")
        if href.startswith("/"):
            href = f"https://www.f6s.com{href}"
        org = org_el.get_text(strip=True) if org_el else "F6S Partner"
        desc = desc_el.get_text(strip=True)[:200] if desc_el else ""

        opps.append(
            normalize_opp(
                {
                    "name": name,
                    "organization": org,
                    "category": "Accelerator",
                    "type": "accelerator",
                    "country": "Global",
                    "link": href,
                    "source": "f6s.com",
                    "description": desc,
                    "tags": ["f6s", "startup-program"],
                }
            )
        )

    log.info(f"F6S: {len(opps)} opportunities")
    return opps


# ---- Source: Google News RSS (global startup opportunities) ----

def scrape_google_news():
    log.info("Scraping Google News RSS for startup opportunities...")
    opps = []

    queries = [
        ("startup+competition+2026", "competition", "Global"),
        ("startup+grant+2026", "grant", "Global"),
        ("accelerator+program+applications+open", "accelerator", "Global"),
        ("startup+hackathon+prize+2026", "hackathon", "Global"),
        ("fellowship+startup+founders+2026", "fellowship", "Global"),
    ]

    for q, opp_type, country in queries:
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        resp = safe_get(url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:5]

        for item in items:
            title = item.find("title")
            link = item.find("link")
            source_el = item.find("source")

            if not title or not link:
                continue

            name = re.sub(r"\s*-\s*[^-]+$", "", title.get_text(strip=True))
            link_val = link.get_text(strip=True)
            org = source_el.get_text(strip=True) if source_el else "News Source"

            opps.append(
                normalize_opp(
                    {
                        "name": name[:100],
                        "organization": org,
                        "category": opp_type.title(),
                        "type": opp_type,
                        "country": country,
                        "link": link_val,
                        "source": "news.google.com",
                        "description": f"Recent news: {name[:200]}",
                        "tags": ["news", opp_type],
                    }
                )
            )

        time.sleep(0.5)

    log.info(f"Google News (global): {len(opps)} opportunities")
    return opps


# ---- Source: EU EIC ----

def scrape_eic():
    log.info("Scraping EIC opportunities...")
    opps = []
    url = "https://eic.ec.europa.eu/eic-funding-opportunities_en"
    resp = safe_get(url)
    if not resp:
        return opps

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select(".opportunity-item, .call-item, article")[:8]

    for card in cards:
        title_el = card.select_one("h2, h3, h4")
        link_el = card.select_one("a[href]")
        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        href = link_el.get("href", "") if link_el else "https://eic.ec.europa.eu"
        if href.startswith("/"):
            href = f"https://eic.ec.europa.eu{href}"

        opps.append(
            normalize_opp(
                {
                    "name": name[:100],
                    "organization": "European Innovation Council",
                    "category": "Grant",
                    "type": "grant",
                    "country": "Europe",
                    "prize": "€150K–€2.5M",
                    "link": href,
                    "source": "eic.ec.europa.eu",
                    "description": "EU EIC funding for deep tech and innovative startups.",
                    "tags": ["eu", "deep-tech", "non-dilutive"],
                }
            )
        )

    log.info(f"EIC: {len(opps)} opportunities")
    return opps


# ---- Source: Seedstars ----

def scrape_seedstars():
    log.info("Scraping Seedstars...")
    opps = []
    url = "https://www.seedstars.com/programs/"
    resp = safe_get(url)
    if not resp:
        return opps

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("article, .program-card, .opportunity")[:10]

    for card in cards:
        title_el = card.select_one("h2, h3, .title")
        link_el = card.select_one("a")
        desc_el = card.select_one("p, .desc")

        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        href = link_el.get("href", "https://www.seedstars.com") if link_el else "https://www.seedstars.com"
        if href.startswith("/"):
            href = f"https://www.seedstars.com{href}"
        desc = desc_el.get_text(strip=True)[:200] if desc_el else ""

        opps.append(
            normalize_opp(
                {
                    "name": name,
                    "organization": "Seedstars",
                    "category": "Competition",
                    "type": "competition",
                    "country": "Global",
                    "prize": "Up to $500,000",
                    "link": href,
                    "source": "seedstars.com",
                    "description": desc or "Seedstars startup competition for emerging market entrepreneurs.",
                    "tags": ["emerging-markets", "investment", "global"],
                }
            )
        )

    log.info(f"Seedstars: {len(opps)} opportunities")
    return opps


# ============================================================
# PAKISTAN-SPECIFIC SCRAPERS
# ============================================================

def scrape_pakistan_opportunities():
    """
    Scrape Pakistan startup opportunities via Google News RSS
    using Pakistan region parameters.
    """
    log.info("Scraping Pakistan opportunities via Google News RSS...")
    opps = []

    queries = [
        ("startup+competition+Pakistan", "competition"),
        ("startup+grant+Pakistan", "grant"),
        ("accelerator+program+Pakistan+2026", "accelerator"),
        ("hackathon+Pakistan+2026", "hackathon"),
        ("fellowship+Pakistan+startup", "fellowship"),
        ("startup+funding+Pakistan", "funding"),
        ("SMEDA+startup+Pakistan", "grant"),
        ("PITB+startup+competition", "competition"),
        ("HEC+entrepreneurship+grant", "grant"),
        ("NIC+Pakistan+incubation", "accelerator"),
    ]

    for q, opp_type in queries:
        url = (
            f"https://news.google.com/rss/search"
            f"?q={q}&hl=en-PK&gl=PK&ceid=PK:en"
        )
        resp = safe_get(url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:5]

        for item in items:
            title = item.find("title")
            link = item.find("link")
            source_el = item.find("source")

            if not title or not link:
                continue

            name = re.sub(r"\s*-\s*[^-]+$", "", title.get_text(strip=True))
            link_val = link.get_text(strip=True)
            org = source_el.get_text(strip=True) if source_el else "Pakistan News"

            if len(name) < 10:
                continue

            opps.append(
                normalize_opp(
                    {
                        "name": name[:100],
                        "organization": org,
                        "category": opp_type.title(),
                        "type": opp_type,
                        "country": "Pakistan",
                        "link": link_val,
                        "source": "news.google.com",
                        "description": f"Pakistan startup opportunity: {name[:200]}",
                        "tags": ["pakistan", opp_type, "national"],
                    }
                )
            )

        time.sleep(0.5)

    log.info(f"Pakistan (Google News): {len(opps)} opportunities")
    return opps


def scrape_ignite():
    """Scrape Ignite Pakistan for startup programs and grants."""
    log.info("Scraping Ignite Pakistan...")
    opps = []

    urls = [
        "https://ignite.org.pk/programs/",
        "https://ignite.org.pk/grants/",
        "https://ignite.org.pk/competitions/",
        "https://ignite.org.pk/",
    ]

    for url in urls:
        resp = safe_get(url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try multiple card selectors
        cards = soup.select(
            "article, .program, .grant, .competition, "
            ".card, .opportunity, .post, .entry"
        )[:10]

        for card in cards:
            title_el = card.select_one("h1, h2, h3, h4, .title, .entry-title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p, .excerpt, .description, .content")

            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            if len(name) < 5 or len(name) > 200:
                continue

            href = link_el.get("href", "") if link_el else url
            if href.startswith("/"):
                href = f"https://ignite.org.pk{href}"
            elif not href.startswith("http"):
                href = url

            desc = desc_el.get_text(strip=True)[:250] if desc_el else (
                "Ignite Pakistan startup program offering funding and support for tech entrepreneurs."
            )

            # Infer type from URL or content
            opp_type = "grant"
            if "competition" in url or "competition" in name.lower():
                opp_type = "competition"
            elif "program" in url or "accelerat" in name.lower():
                opp_type = "accelerator"

            opps.append(
                normalize_opp(
                    {
                        "name": name,
                        "organization": "Ignite National Technology Fund",
                        "category": opp_type.title(),
                        "type": opp_type,
                        "country": "Pakistan",
                        "link": href,
                        "source": "ignite.org.pk",
                        "description": desc,
                        "tags": ["pakistan", "ignite", "national", "technology"],
                    }
                )
            )

        # Also scrape main page headings if no cards found
        if not cards:
            headings = soup.select("h2, h3")[:8]
            for h in headings:
                text = h.get_text(strip=True)
                if len(text) > 15 and any(
                    kw in text.lower()
                    for kw in ["program", "grant", "competition", "fund", "startup", "tech", "innovat"]
                ):
                    link_el = h.find_parent("a") or h.find("a")
                    href = ""
                    if link_el:
                        href = link_el.get("href", "")
                        if href.startswith("/"):
                            href = f"https://ignite.org.pk{href}"

                    opps.append(
                        normalize_opp(
                            {
                                "name": text[:100],
                                "organization": "Ignite National Technology Fund",
                                "category": "Grant",
                                "type": "grant",
                                "country": "Pakistan",
                                "link": href or "https://ignite.org.pk",
                                "source": "ignite.org.pk",
                                "description": "Ignite Pakistan funding and support for technology startups.",
                                "tags": ["pakistan", "ignite", "national"],
                            }
                        )
                    )

        time.sleep(1)

    log.info(f"Ignite Pakistan: {len(opps)} opportunities")
    return opps


def scrape_nic_pakistan():
    """Scrape National Incubation Center Pakistan programs."""
    log.info("Scraping NIC Pakistan...")
    opps = []

    nic_sites = [
        ("https://nicpakistan.pk", "NIC Pakistan", "nicpakistan.pk"),
        ("https://niclahore.pk", "NIC Lahore", "niclahore.pk"),
        ("https://nickarachi.com", "NIC Karachi", "nickarachi.com"),
    ]

    for url, org_name, source in nic_sites:
        resp = safe_get(url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select(
            "article, .program, .cohort, .batch, .card, .service, "
            ".opportunity, .post, section.programs > div"
        )[:10]

        for card in cards:
            title_el = card.select_one("h1, h2, h3, h4, .title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p, .excerpt, .desc")

            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            if len(name) < 5:
                continue

            href = link_el.get("href", "") if link_el else url
            if href.startswith("/"):
                href = f"{url.rstrip('/')}{href}"
            elif not href.startswith("http"):
                href = url

            desc = desc_el.get_text(strip=True)[:250] if desc_el else (
                f"{org_name} incubation program supporting early-stage Pakistani startups."
            )

            opps.append(
                normalize_opp(
                    {
                        "name": name[:100],
                        "organization": org_name,
                        "category": "Accelerator",
                        "type": "accelerator",
                        "country": "Pakistan",
                        "link": href,
                        "source": source,
                        "description": desc,
                        "tags": ["pakistan", "nic", "incubation", "national"],
                    }
                )
            )

        # Fallback: grab page title + description if no structured cards
        if not opps or all(o["source"] != source for o in opps):
            page_title = soup.find("title")
            meta_desc = soup.find("meta", attrs={"name": "description"})
            name = page_title.get_text(strip=True) if page_title else org_name
            desc = meta_desc.get("content", "") if meta_desc else (
                f"{org_name} — Pakistan's premier startup incubation center."
            )
            opps.append(
                normalize_opp(
                    {
                        "name": f"{org_name} Incubation Program",
                        "organization": org_name,
                        "category": "Accelerator",
                        "type": "accelerator",
                        "country": "Pakistan",
                        "link": url,
                        "source": source,
                        "description": desc[:250],
                        "tags": ["pakistan", "nic", "incubation"],
                    }
                )
            )

        time.sleep(1)

    log.info(f"NIC Pakistan: {len(opps)} opportunities")
    return opps


def scrape_plan9():
    """Scrape Plan9 PITB startup incubator programs."""
    log.info("Scraping Plan9 / PITB...")
    opps = []

    urls = [
        ("https://plan9.pitb.gov.pk", "Plan9 - PITB", "plan9.pitb.gov.pk"),
        ("https://pitb.gov.pk/startups", "PITB", "pitb.gov.pk"),
        ("https://pitb.gov.pk/plan9", "PITB Plan9", "pitb.gov.pk"),
    ]

    for url, org_name, source in urls:
        resp = safe_get(url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select("article, .program, .card, .cohort, .opportunity, .post")[:8]

        for card in cards:
            title_el = card.select_one("h1, h2, h3, h4, .title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p, .excerpt")

            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            if len(name) < 5:
                continue

            href = link_el.get("href", "") if link_el else url
            if href.startswith("/"):
                base = re.match(r"https?://[^/]+", url)
                href = f"{base.group(0)}{href}" if base else url
            elif not href.startswith("http"):
                href = url

            desc = desc_el.get_text(strip=True)[:250] if desc_el else (
                f"{org_name} startup incubation program by Punjab Information Technology Board."
            )

            opps.append(
                normalize_opp(
                    {
                        "name": name[:100],
                        "organization": org_name,
                        "category": "Accelerator",
                        "type": "accelerator",
                        "country": "Pakistan",
                        "link": href,
                        "source": source,
                        "description": desc,
                        "tags": ["pakistan", "plan9", "pitb", "punjab", "incubation"],
                    }
                )
            )

        # Guaranteed fallback entry
        if not any(o["source"] == source for o in opps):
            opps.append(
                normalize_opp(
                    {
                        "name": f"{org_name} Startup Incubation Program",
                        "organization": org_name,
                        "category": "Accelerator",
                        "type": "accelerator",
                        "country": "Pakistan",
                        "link": url,
                        "source": source,
                        "description": (
                            "Plan9 by PITB is one of Pakistan's largest technology incubators, "
                            "providing office space, mentorship, and funding support."
                        ),
                        "tags": ["pakistan", "plan9", "pitb", "lahore"],
                    }
                )
            )

        time.sleep(1)

    log.info(f"Plan9/PITB: {len(opps)} opportunities")
    return opps


def scrape_hec_pakistan():
    """Scrape HEC Pakistan entrepreneurship and research grants."""
    log.info("Scraping HEC Pakistan...")
    opps = []

    urls = [
        "https://hec.gov.pk/english/services/students/NRPU/Pages/default.aspx",
        "https://hec.gov.pk/english/services/startups/Pages/default.aspx",
        "https://hec.gov.pk/english/services/students/entrepreneurship/Pages/default.aspx",
        "https://hec.gov.pk",
    ]

    for url in urls:
        resp = safe_get(url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select(
            "article, .program-item, .card, li.item, .announcement, "
            ".news-item, table tr, .scheme"
        )[:10]

        for card in cards:
            title_el = card.select_one("h1, h2, h3, h4, a, td, .title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p, .desc, td + td")

            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            if len(name) < 8 or len(name) > 200:
                continue

            if not any(
                kw in name.lower()
                for kw in ["grant", "fund", "research", "startup", "entrepreneur", "innovat", "program", "scheme"]
            ):
                continue

            href = link_el.get("href", "") if link_el else ""
            if href.startswith("/"):
                href = f"https://hec.gov.pk{href}"
            elif not href.startswith("http"):
                href = "https://hec.gov.pk"

            desc = desc_el.get_text(strip=True)[:250] if desc_el else (
                "HEC Pakistan grant/program for higher education and startup ecosystem."
            )

            opps.append(
                normalize_opp(
                    {
                        "name": name[:100],
                        "organization": "Higher Education Commission Pakistan",
                        "category": "Grant",
                        "type": "grant",
                        "country": "Pakistan",
                        "link": href or "https://hec.gov.pk",
                        "source": "hec.gov.pk",
                        "description": desc,
                        "tags": ["pakistan", "hec", "research", "education"],
                    }
                )
            )

        time.sleep(1)

    # Guaranteed fallback
    if not opps:
        opps.append(
            normalize_opp(
                {
                    "name": "HEC Technology Development Fund",
                    "organization": "Higher Education Commission Pakistan",
                    "category": "Grant",
                    "type": "grant",
                    "country": "Pakistan",
                    "prize": "Varies",
                    "link": "https://hec.gov.pk",
                    "source": "hec.gov.pk",
                    "description": (
                        "HEC Pakistan offers various grants for research, technology development, "
                        "and startup support through universities."
                    ),
                    "tags": ["pakistan", "hec", "grant", "research"],
                }
            )
        )

    log.info(f"HEC Pakistan: {len(opps)} opportunities")
    return opps


def scrape_stza():
    """Scrape STZA (Special Technology Zones Authority) Pakistan."""
    log.info("Scraping STZA Pakistan...")
    opps = []

    resp = safe_get("https://stza.gov.pk")
    if not resp:
        # Guaranteed fallback
        opps.append(
            normalize_opp(
                {
                    "name": "STZA Special Technology Zone Incentives",
                    "organization": "Special Technology Zones Authority",
                    "category": "Funding",
                    "type": "funding",
                    "country": "Pakistan",
                    "prize": "Tax exemptions + grants",
                    "link": "https://stza.gov.pk",
                    "source": "stza.gov.pk",
                    "description": (
                        "STZA offers tax incentives, funding, and support for technology companies "
                        "operating in Pakistan's Special Technology Zones."
                    ),
                    "tags": ["pakistan", "stza", "sez", "technology-zone"],
                }
            )
        )
        return opps

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("article, .program, .card, .opportunity, .zone, .incentive")[:8]

    for card in cards:
        title_el = card.select_one("h1, h2, h3, h4, .title")
        link_el = card.select_one("a[href]")
        desc_el = card.select_one("p, .desc")

        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        if len(name) < 5:
            continue

        href = link_el.get("href", "") if link_el else "https://stza.gov.pk"
        if href.startswith("/"):
            href = f"https://stza.gov.pk{href}"

        desc = desc_el.get_text(strip=True)[:250] if desc_el else (
            "STZA special technology zone incentive for tech startups and companies in Pakistan."
        )

        opps.append(
            normalize_opp(
                {
                    "name": name[:100],
                    "organization": "Special Technology Zones Authority",
                    "category": "Funding",
                    "type": "funding",
                    "country": "Pakistan",
                    "link": href,
                    "source": "stza.gov.pk",
                    "description": desc,
                    "tags": ["pakistan", "stza", "sez", "technology"],
                }
            )
        )

    if not opps:
        opps.append(
            normalize_opp(
                {
                    "name": "STZA Technology Zone Startup Program",
                    "organization": "Special Technology Zones Authority",
                    "category": "Funding",
                    "type": "funding",
                    "country": "Pakistan",
                    "prize": "Tax exemptions + incentives",
                    "link": "https://stza.gov.pk",
                    "source": "stza.gov.pk",
                    "description": (
                        "STZA provides tax exemptions, funding support, and infrastructure "
                        "for tech startups in Pakistan's Special Technology Zones."
                    ),
                    "tags": ["pakistan", "stza", "technology-zone"],
                }
            )
        )

    log.info(f"STZA: {len(opps)} opportunities")
    return opps


def scrape_invest2innovate():
    """Scrape Invest2Innovate Pakistan programs."""
    log.info("Scraping Invest2Innovate Pakistan...")
    opps = []

    urls = [
        "https://invest2innovate.com/programs/",
        "https://invest2innovate.com/",
    ]

    for url in urls:
        resp = safe_get(url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("article, .program, .card, .opportunity, .post, .entry")[:10]

        for card in cards:
            title_el = card.select_one("h1, h2, h3, h4, .title, .entry-title")
            link_el = card.select_one("a[href]")
            desc_el = card.select_one("p, .excerpt, .desc")

            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            if len(name) < 5:
                continue

            href = link_el.get("href", "") if link_el else url
            if href.startswith("/"):
                href = f"https://invest2innovate.com{href}"
            elif not href.startswith("http"):
                href = url

            desc = desc_el.get_text(strip=True)[:250] if desc_el else (
                "Invest2Innovate program supporting Pakistan's startup ecosystem."
            )

            opps.append(
                normalize_opp(
                    {
                        "name": name[:100],
                        "organization": "Invest2Innovate (i2i)",
                        "category": "Accelerator",
                        "type": "accelerator",
                        "country": "Pakistan",
                        "link": href,
                        "source": "invest2innovate.com",
                        "description": desc,
                        "tags": ["pakistan", "i2i", "accelerator", "impact"],
                    }
                )
            )

        time.sleep(1)

    # Guaranteed fallback
    if not opps:
        opps.append(
            normalize_opp(
                {
                    "name": "i2i Accelerator Pakistan",
                    "organization": "Invest2Innovate (i2i)",
                    "category": "Accelerator",
                    "type": "accelerator",
                    "country": "Pakistan",
                    "prize": "Mentorship + Funding",
                    "link": "https://invest2innovate.com",
                    "source": "invest2innovate.com",
                    "description": (
                        "Invest2Innovate (i2i) is a leading startup accelerator in Pakistan "
                        "focused on impact-driven entrepreneurs and social enterprises."
                    ),
                    "tags": ["pakistan", "i2i", "impact", "social-enterprise"],
                }
            )
        )

    log.info(f"Invest2Innovate: {len(opps)} opportunities")
    return opps


def scrape_pakistan_news_extra():
    """
    Additional Pakistan startup opportunity scraping from
    Dawn, The News, ARY, Express Tribune tech sections via RSS.
    """
    log.info("Scraping Pakistani news outlets for startup opportunities...")
    opps = []

    rss_feeds = [
        ("https://www.dawn.com/feeds/technology", "Dawn", "dawn.com"),
        ("https://tribune.com.pk/feed/technology", "Express Tribune", "tribune.com.pk"),
        ("https://arynews.tv/feed/", "ARY News", "arynews.tv"),
    ]

    keywords = ["startup", "grant", "competition", "accelerator", "incubat", "fellowship", "hackathon", "fund"]

    for feed_url, org_name, source in rss_feeds:
        resp = safe_get(feed_url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:10]

        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")

            if not title_el:
                continue

            name = title_el.get_text(strip=True)

            if not any(kw in name.lower() for kw in keywords):
                continue

            link_val = link_el.get_text(strip=True) if link_el else ""
            desc = BeautifulSoup(
                desc_el.get_text(strip=True) if desc_el else "", "html.parser"
            ).get_text()[:200]

            # Infer type
            opp_type = "competition"
            if "grant" in name.lower() or "fund" in name.lower():
                opp_type = "grant"
            elif "accelerat" in name.lower() or "incubat" in name.lower():
                opp_type = "accelerator"
            elif "hackathon" in name.lower():
                opp_type = "hackathon"
            elif "fellowship" in name.lower():
                opp_type = "fellowship"

            opps.append(
                normalize_opp(
                    {
                        "name": name[:100],
                        "organization": org_name,
                        "category": opp_type.title(),
                        "type": opp_type,
                        "country": "Pakistan",
                        "link": link_val,
                        "source": source,
                        "description": desc or name,
                        "tags": ["pakistan", "news", opp_type],
                    }
                )
            )

        time.sleep(0.5)

    log.info(f"Pakistan news extra: {len(opps)} opportunities")
    return opps


# ---- Deduplicate ----

def deduplicate(opportunities):
    seen_ids = set()
    seen_names = set()
    unique = []

    for opp in opportunities:
        oid = opp.get("id", "")
        name_key = opp.get("name", "").lower().strip()

        if oid in seen_ids or name_key in seen_names:
            continue

        seen_ids.add(oid)
        if name_key:
            seen_names.add(name_key)
        unique.append(opp)

    return unique


# ---- Load existing data ----

def load_existing():
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                data = json.load(f)
                return data.get("opportunities", [])
        except Exception as e:
            log.warning(f"Could not load existing data: {e}")
    return []


# ---- Save ----

def save(opportunities):
    data = {
        "last_updated": now_iso(),
        "total": len(opportunities),
        "opportunities": opportunities,
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"Saved {len(opportunities)} opportunities to {OUTPUT_FILE}")


# ---- Main ----

def main():
    log.info("=== LaunchPad Intelligence Scraper Starting ===")

    # Load existing to preserve curated data
    existing = load_existing()
    log.info(f"Loaded {len(existing)} existing opportunities")

    # All scrapers — international + Pakistan
    scrapers = [
        # International
        scrape_devpost,
        scrape_challenge_gov,
        scrape_f6s,
        scrape_google_news,
        scrape_eic,
        scrape_seedstars,
        # Pakistan national
        scrape_pakistan_opportunities,
        scrape_ignite,
        scrape_nic_pakistan,
        scrape_plan9,
        scrape_hec_pakistan,
        scrape_stza,
        scrape_invest2innovate,
        scrape_pakistan_news_extra,
    ]

    new_opps = []
    for scraper in scrapers:
        try:
            result = scraper()
            new_opps.extend(result)
        except Exception as e:
            log.error(f"Scraper {scraper.__name__} failed: {e}")
        time.sleep(1)

    log.info(f"Scraped {len(new_opps)} new opportunities total")

    # Merge: existing + new
    all_opps = existing + new_opps
    unique = deduplicate(all_opps)

    # Filter out empties
    unique = [o for o in unique if o.get("name") and len(o["name"]) > 3]

    # Sort by date added desc
    unique.sort(
        key=lambda o: o.get("date_added", ""),
        reverse=True,
    )

    # Log summary
    pk_count = sum(1 for o in unique if o.get("country") == "Pakistan")
    intl_count = len(unique) - pk_count
    log.info(f"Final: {len(unique)} unique ({pk_count} Pakistan, {intl_count} International)")

    save(unique)
    log.info("=== Scraper Complete ===")


if __name__ == "__main__":
    main()
