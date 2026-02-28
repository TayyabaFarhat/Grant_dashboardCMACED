"""
LaunchPad Intelligence — Social & LinkedIn Scraper
Scrapes startup opportunities from social platforms using public RSS and search.
Covers both Pakistan (national) and international opportunities.
"""

import logging
import re
import time
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("social_scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 15


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_get(url):
    try:
        resp = SESSION.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp
    except Exception as e:
        log.warning(f"Failed: {url} → {e}")
        return None


# ---- Twitter/X Public RSS via Nitter ----

def scrape_twitter_opportunities():
    """Scrape startup opportunity tweets via Nitter (public RSS proxy)."""
    log.info("Scraping Twitter/X via public RSS...")
    opps = []

    nitter_instances = [
        "https://nitter.privacydev.net",
        "https://nitter.poast.org",
        "https://nitter.1d4.us",
    ]

    search_terms = [
        ("startup+grant+applications+open", "grant", "Global"),
        ("accelerator+program+apply+now", "accelerator", "Global"),
        ("startup+competition+deadline", "competition", "Global"),
        ("Pakistan+startup+grant+competition", "competition", "Pakistan"),
        ("Pakistan+accelerator+program", "accelerator", "Pakistan"),
    ]

    for instance in nitter_instances[:1]:
        for term, opp_type, country in search_terms:
            url = f"{instance}/search/rss?q={term}&f=tweets"
            resp = safe_get(url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "xml")
            items = soup.find_all("item")[:5]

            for item in items:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")

                if not title_el:
                    continue

                text = title_el.get_text(strip=True)
                if len(text) < 20:
                    continue

                opps.append({
                    "id": f"tw_{hash(text) % 10**8:08d}",
                    "name": text[:80],
                    "organization": "Twitter/X Community",
                    "category": opp_type.title(),
                    "type": opp_type,
                    "country": country,
                    "deadline": "",
                    "prize": "Varies",
                    "link": link_el.get_text(strip=True) if link_el else "",
                    "source": "twitter.com",
                    "date_added": now_iso(),
                    "status": "open",
                    "description": (desc_el.get_text(strip=True) if desc_el else text)[:200],
                    "tags": ["social", "twitter", country.lower()],
                })

            time.sleep(0.5)

    log.info(f"Twitter/X: {len(opps)} opportunities")
    return opps


# ---- LinkedIn: Global Opportunities ----

def scrape_linkedin_opportunities():
    """
    Scrape LinkedIn global startup opportunities via Google News proxy.
    """
    log.info("Scraping LinkedIn global opportunity signals...")
    opps = []

    url = (
        "https://news.google.com/rss/search?"
        "q=site:linkedin.com+startup+competition+grant+accelerator&"
        "hl=en-US&gl=US&ceid=US:en"
    )
    resp = safe_get(url)
    if not resp:
        return opps

    soup = BeautifulSoup(resp.text, "xml")
    items = soup.find_all("item")[:8]

    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")

        if not title_el:
            continue

        text = title_el.get_text(strip=True)
        text = re.sub(r"\s*-\s*LinkedIn$", "", text).strip()

        if len(text) < 10:
            continue

        opps.append({
            "id": f"li_{hash(text) % 10**8:08d}",
            "name": text[:100],
            "organization": "LinkedIn",
            "category": "Competition",
            "type": "competition",
            "country": "Global",
            "deadline": "",
            "prize": "Varies",
            "link": link_el.get_text(strip=True) if link_el else "",
            "source": "linkedin.com",
            "date_added": now_iso(),
            "status": "open",
            "description": f"Startup opportunity shared on LinkedIn: {text[:200]}",
            "tags": ["linkedin", "professional", "global"],
        })

    log.info(f"LinkedIn (global): {len(opps)} opportunities")
    return opps


# ---- LinkedIn: Pakistan Opportunities ----

def scrape_linkedin_pakistan():
    """
    Scrape LinkedIn Pakistan startup opportunities via Google News
    with Pakistan region parameters.
    """
    log.info("Scraping LinkedIn Pakistan opportunity signals...")
    opps = []

    queries = [
        "site:linkedin.com startup competition grant accelerator Pakistan",
        "site:linkedin.com Pakistan startup fellowship hackathon",
        "site:linkedin.com PITB NIC ignite Pakistan program",
    ]

    for q in queries:
        encoded_q = q.replace(" ", "+")
        url = (
            f"https://news.google.com/rss/search?"
            f"q={encoded_q}&hl=en-PK&gl=PK&ceid=PK:en"
        )
        resp = safe_get(url)
        if not resp:
            time.sleep(0.5)
            continue

        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:6]

        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")

            if not title_el:
                continue

            text = title_el.get_text(strip=True)
            text = re.sub(r"\s*-\s*LinkedIn$", "", text).strip()

            if len(text) < 10:
                continue

            # Infer type
            opp_type = "competition"
            name_lower = text.lower()
            if "grant" in name_lower or "fund" in name_lower:
                opp_type = "grant"
            elif "accelerat" in name_lower or "incubat" in name_lower:
                opp_type = "accelerator"
            elif "hackathon" in name_lower:
                opp_type = "hackathon"
            elif "fellowship" in name_lower:
                opp_type = "fellowship"

            opps.append({
                "id": f"lipk_{hash(text) % 10**8:08d}",
                "name": text[:100],
                "organization": "LinkedIn Pakistan",
                "category": opp_type.title(),
                "type": opp_type,
                "country": "Pakistan",
                "deadline": "",
                "prize": "Varies",
                "link": link_el.get_text(strip=True) if link_el else "",
                "source": "linkedin.com",
                "date_added": now_iso(),
                "status": "open",
                "description": f"Pakistan startup opportunity on LinkedIn: {text[:200]}",
                "tags": ["linkedin", "pakistan", "national", opp_type],
            })

        time.sleep(0.5)

    log.info(f"LinkedIn (Pakistan): {len(opps)} opportunities")
    return opps


# ---- Facebook: Global Public Groups ----

def scrape_facebook_opportunities():
    """
    Facebook public startup community signals via news search proxy.
    """
    log.info("Scraping Facebook public startup signals via RSS bridge...")
    opps = []

    url = (
        "https://news.google.com/rss/search?"
        "q=startup+competition+grant+2026+facebook&"
        "hl=en-US&gl=US&ceid=US:en"
    )
    resp = safe_get(url)
    if not resp:
        return opps

    soup = BeautifulSoup(resp.text, "xml")
    items = soup.find_all("item")[:5]

    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")

        if not title_el:
            continue

        text = title_el.get_text(strip=True)
        if not any(
            w in text.lower()
            for w in ["startup", "grant", "competition", "accelerator", "hackathon"]
        ):
            continue

        opps.append({
            "id": f"fb_{hash(text) % 10**8:08d}",
            "name": text[:100],
            "organization": "Facebook Community",
            "category": "Competition",
            "type": "competition",
            "country": "Global",
            "deadline": "",
            "prize": "Varies",
            "link": link_el.get_text(strip=True) if link_el else "",
            "source": "facebook.com",
            "date_added": now_iso(),
            "status": "open",
            "description": f"Startup opportunity from social media: {text[:200]}",
            "tags": ["social", "community", "global"],
        })

    log.info(f"Facebook (global): {len(opps)} opportunities")
    return opps


# ---- Facebook: Pakistan Public Groups ----

def scrape_facebook_pakistan():
    """
    Facebook Pakistan startup community signals via news proxy.
    """
    log.info("Scraping Facebook Pakistan startup signals...")
    opps = []

    url = (
        "https://news.google.com/rss/search?"
        "q=startup+competition+grant+Pakistan+facebook&"
        "hl=en-PK&gl=PK&ceid=PK:en"
    )
    resp = safe_get(url)
    if not resp:
        return opps

    soup = BeautifulSoup(resp.text, "xml")
    items = soup.find_all("item")[:5]

    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")

        if not title_el:
            continue

        text = title_el.get_text(strip=True)
        if not any(
            w in text.lower()
            for w in ["startup", "grant", "competition", "accelerator", "pakistan", "incubat"]
        ):
            continue

        # Infer type
        opp_type = "competition"
        tl = text.lower()
        if "grant" in tl or "fund" in tl:
            opp_type = "grant"
        elif "accelerat" in tl or "incubat" in tl:
            opp_type = "accelerator"
        elif "hackathon" in tl:
            opp_type = "hackathon"

        opps.append({
            "id": f"fbpk_{hash(text) % 10**8:08d}",
            "name": text[:100],
            "organization": "Facebook Pakistan Community",
            "category": opp_type.title(),
            "type": opp_type,
            "country": "Pakistan",
            "deadline": "",
            "prize": "Varies",
            "link": link_el.get_text(strip=True) if link_el else "",
            "source": "facebook.com",
            "date_added": now_iso(),
            "status": "open",
            "description": f"Pakistan startup opportunity from social media: {text[:200]}",
            "tags": ["facebook", "pakistan", "social", opp_type],
        })

    log.info(f"Facebook (Pakistan): {len(opps)} opportunities")
    return opps


# ---- Reddit: Global Public Subreddits ----

def scrape_reddit_opportunities():
    """Scrape Reddit public subreddits for startup opportunities."""
    log.info("Scraping Reddit public subreddits...")
    opps = []

    subreddits = [
        ("r/startups", "Global"),
        ("r/entrepreneur", "Global"),
        ("r/smallbusiness", "Global"),
    ]

    for sub, country in subreddits:
        url = f"https://www.reddit.com/{sub}/search.rss?q=grant+competition+accelerator+fellowship&sort=new"
        resp = safe_get(url)
        if not resp:
            time.sleep(1)
            continue

        soup = BeautifulSoup(resp.text, "xml")
        entries = soup.find_all("entry")[:5]

        for entry in entries:
            title_el = entry.find("title")
            link_el = entry.find("link")
            content_el = entry.find("content")

            if not title_el:
                continue

            text = title_el.get_text(strip=True)
            if not any(
                w in text.lower()
                for w in ["grant", "competition", "accelerator", "fellowship", "hackathon", "prize", "funding"]
            ):
                continue

            href = link_el.get("href", "") if link_el else ""
            desc = BeautifulSoup(
                content_el.get_text(strip=True) if content_el else "", "html.parser"
            ).get_text()[:200]

            opps.append({
                "id": f"rd_{hash(text) % 10**8:08d}",
                "name": text[:100],
                "organization": f"Reddit {sub}",
                "category": "Community",
                "type": "competition",
                "country": country,
                "deadline": "",
                "prize": "Varies",
                "link": href,
                "source": "reddit.com",
                "date_added": now_iso(),
                "status": "open",
                "description": desc or text[:200],
                "tags": ["reddit", "community", country.lower()],
            })

        time.sleep(1)

    log.info(f"Reddit (global): {len(opps)} opportunities")
    return opps


# ---- Reddit: Pakistan-focused search ----

def scrape_reddit_pakistan():
    """Scrape Reddit for Pakistan startup opportunities."""
    log.info("Scraping Reddit for Pakistan opportunities...")
    opps = []

    search_terms = [
        "Pakistan+startup+competition",
        "Pakistan+grant+accelerator",
        "PITB+NIC+startup+Pakistan",
    ]

    for term in search_terms:
        url = (
            f"https://www.reddit.com/search.rss?"
            f"q={term}&sort=new&type=link"
        )
        resp = safe_get(url)
        if not resp:
            time.sleep(1)
            continue

        soup = BeautifulSoup(resp.text, "xml")
        entries = soup.find_all("entry")[:4]

        for entry in entries:
            title_el = entry.find("title")
            link_el = entry.find("link")
            content_el = entry.find("content")

            if not title_el:
                continue

            text = title_el.get_text(strip=True)
            if len(text) < 10:
                continue

            href = link_el.get("href", "") if link_el else ""
            desc = BeautifulSoup(
                content_el.get_text(strip=True) if content_el else "", "html.parser"
            ).get_text()[:200]

            opp_type = "competition"
            tl = text.lower()
            if "grant" in tl or "fund" in tl:
                opp_type = "grant"
            elif "accelerat" in tl or "incubat" in tl:
                opp_type = "accelerator"
            elif "hackathon" in tl:
                opp_type = "hackathon"

            opps.append({
                "id": f"rdpk_{hash(text) % 10**8:08d}",
                "name": text[:100],
                "organization": "Reddit Pakistan Community",
                "category": opp_type.title(),
                "type": opp_type,
                "country": "Pakistan",
                "deadline": "",
                "prize": "Varies",
                "link": href,
                "source": "reddit.com",
                "date_added": now_iso(),
                "status": "open",
                "description": desc or f"Pakistan startup opportunity: {text[:200]}",
                "tags": ["reddit", "pakistan", opp_type],
            })

        time.sleep(1)

    log.info(f"Reddit (Pakistan): {len(opps)} opportunities")
    return opps


def get_all_social_opportunities():
    """Run all social scrapers and return combined results."""
    all_opps = []

    scrapers = [
        # Global
        scrape_linkedin_opportunities,
        scrape_reddit_opportunities,
        scrape_facebook_opportunities,
        # Pakistan
        scrape_linkedin_pakistan,
        scrape_facebook_pakistan,
        scrape_reddit_pakistan,
        # scrape_twitter_opportunities,  # Enable if Nitter is accessible
    ]

    for scraper in scrapers:
        try:
            result = scraper()
            all_opps.extend(result)
        except Exception as e:
            log.error(f"{scraper.__name__} failed: {e}")

    pk_count = sum(1 for o in all_opps if o.get("country") == "Pakistan")
    log.info(f"Social scraper total: {len(all_opps)} ({pk_count} Pakistan)")
    return all_opps


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    results = get_all_social_opportunities()
    print(f"\nTotal social opportunities: {len(results)}")
    pk = [r for r in results if r.get("country") == "Pakistan"]
    intl = [r for r in results if r.get("country") != "Pakistan"]
    print(f"  Pakistan: {len(pk)}")
    print(f"  International: {len(intl)}")
    for r in results[:8]:
        print(f"  [{r['country']:12}] {r['name'][:60]}")
