from bs4 import BeautifulSoup
import re
import json
# Fast path: TLS-impersonating HTTP client. Works for plain server-rendered
# pages that aren't behind Cloudflare or similar bot protection.
from curl_cffi import requests as requests_mimic
# Slow path: a real browser, for JS-rendered storefronts and sites that need
# actual JavaScript execution to build the page.
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


# =========================================================================
# GENERIC EXTRACTION — works across most e-commerce sites without needing
# site-specific CSS selectors. Tries three methods, in order of reliability:
#
#   1. JSON-LD structured data (schema.org "Product") — most retailers embed
#      this for Google Shopping / rich search results. When present, it's
#      the most reliable source: consistent field names regardless of the
#      site's actual visual HTML/CSS.
#   2. Open Graph / meta tags (og:title, product:price:amount, etc.) — a
#      common second-choice standard, often present even when JSON-LD isn't.
#   3. A handful of very common CSS patterns (h1 for title; several typical
#      price class/attribute names) as a last-resort guess.
#
# This won't work on literally every site — some have broken markup, load
# everything via obscure internal APIs, or use non-standard structures —
# but it covers the majority of mainstream NZ retailers without you having
# to hand-write selectors for each one.
# =========================================================================

def extract_product_generic(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title, price, currency = None, None, None

    # --- Method 1: JSON-LD structured data ---
    json_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string.strip())
            candidates = []
            if isinstance(data, list):
                candidates = data
            elif isinstance(data, dict) and "@graph" in data:
                candidates = data["@graph"]
            else:
                candidates = [data]

            # Some sites nest a Product inside an ItemList or a single
            # object without @graph — flatten one level deeper just in case.
            flattened = []
            for item in candidates:
                if isinstance(item, dict):
                    flattened.append(item)
                    if "@graph" in item:
                        flattened.extend(item["@graph"])

            product_data = next(
                (item for item in flattened if isinstance(item, dict) and item.get("@type") == "Product"),
                None
            )
            if product_data:
                title = product_data.get("name")
                offers = product_data.get("offers", {})
                if isinstance(offers, list) and len(offers) > 0:
                    offers = offers[0]
                if isinstance(offers, dict):
                    # "price" is standard; "lowPrice" covers AggregateOffer
                    # (a range across variants/sellers) — take the lowest.
                    price = offers.get("price") or offers.get("lowPrice")
                    currency = offers.get("priceCurrency")
                if title and price:
                    break
        except Exception:
            continue

    # --- Method 2: Microdata (itemprop attributes without JSON-LD) ---
    if not title or not price:
        if not title:
            name_el = soup.find(attrs={"itemprop": "name"})
            if name_el:
                title = name_el.get("content") or name_el.text.strip()
        if not price:
            price_el = soup.find(attrs={"itemprop": "price"})
            if price_el:
                price = price_el.get("content") or price_el.text.strip()
            currency_el = soup.find(attrs={"itemprop": "priceCurrency"})
            if currency_el:
                currency = currency or currency_el.get("content")

    # --- Method 3: Open Graph / meta tag fallback ---
    if not title or not price:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = title or og_title["content"].strip()

        # Different sites use different property names for price meta tags
        for prop_name in ["product:price:amount", "og:price:amount", "twitter:data1"]:
            price_meta = soup.find("meta", property=prop_name) or soup.find("meta", attrs={"name": prop_name})
            if price_meta and price_meta.get("content"):
                price = price or price_meta["content"].strip()
                break

    # --- Method 4: Common CSS/DOM fallback patterns ---
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.text.strip()

    if not price:
        # A grab-bag of the most common price container patterns seen
        # across NZ/AU retail sites. Order matters: more specific first.
        price_el = (
            soup.find(attrs={"data-testid": re.compile("price", re.I)})
            or soup.find(class_=re.compile(r'price', re.I))
            or soup.find(class_=re.compile(r'sales', re.I))
        )
        if price_el:
            # Some sites store the actual number in a "content" attribute
            # rather than the visible text (schema.org microdata convention)
            price = price_el.get("content") or price_el.text.strip()

    # --- Method 5: last resort — scan visible text near the title for a
    # currency-looking number. Only used if nothing structured was found at
    # all. This is the least reliable method (could grab an unrelated price,
    # e.g. a "you might also like" item) but means we almost always return
    # *something* rather than nothing on completely non-standard sites.
    if not price:
        body_text = soup.get_text(" ", strip=True)
        price_match = re.search(r'(?:NZ\$|AU\$|\$|NZD)\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)', body_text)
        if price_match:
            price = price_match.group(1)

    if not title:
        # Absolute last resort: the <title> tag, though it often includes
        # the site name suffix (e.g. "Product Name | JB Hi-Fi NZ") which we
        # can't reliably strip without knowing the site.
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.text.strip()

    return title, price, currency


def clean_price(raw_price):
    """Turns messy price text ('$1,299.00', '1299', etc.) into a clean float."""
    if raw_price is None:
        return None
    sanitized = re.sub(r'\s+', '', str(raw_price).strip())
    match = re.search(r'([0-9,]+\.?[0-9]*)', sanitized)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    # Guard against schema.org prices sometimes being given in cents
    if value > 100000 and "." not in match.group(1):
        value = value / 100.0
    return value


def is_bot_wall(page_title: str, html: str) -> bool:
    """
    Detects common bot-protection interstitial pages across several major
    providers, not just Cloudflare. If a fetch shows one of these, the page
    content is a challenge screen, not real product data — any title/price
    we might "find" on it would be garbage, so we should bail out rather
    than return junk.
    """
    title_markers = ["Just a moment", "Attention Required!", "Access Denied", "Are you a human"]
    html_markers = [
        "Performing security verification",
        "challenges.cloudflare.com",   # Cloudflare
        "_Incapsula_Resource",          # Imperva/Incapsula
        "distil_r_captcha",             # Akamai/Distil
        "px-captcha", "perimeterx",     # PerimeterX
        "datadome",                     # DataDome
        "geo.captcha-delivery.com",     # DataDome captcha
        # NOTE: deliberately NOT including generic "recaptcha"/"hcaptcha" —
        # plenty of normal, unblocked pages embed those widgets elsewhere
        # (a newsletter form, a chat widget) without the product page itself
        # being blocked. Those false-positived JB Hi-Fi even after it had
        # worked correctly, since this check ran before extraction was ever
        # attempted. Now this function is only consulted for the error
        # *message* after extraction has already failed on its own merits.
    ]

    if page_title and any(marker.lower() in page_title.lower() for marker in title_markers):
        return True
    if html:
        html_lower = html.lower()
        if any(marker.lower() in html_lower for marker in html_markers):
            return True
    return False


# =========================================================================
# FETCHERS
# =========================================================================

def fetch_html_fast(url: str):
    """Plain HTTP fetch with TLS impersonation. Fast, but can't run JS and
    can't get past Cloudflare's JS challenge pages."""
    try:
        response = requests_mimic.get(url, impersonate="chrome", timeout=15)
        return response.content.decode(errors="ignore"), response.status_code
    except Exception as e:
        print(f"⚠️ Fast fetch failed: {e}")
        return None, None


def fetch_html_with_chromium_stealth(url: str, wait_selector: str = None, wait_selector_timeout: int = 5000):
    """Launches a real Chromium browser with playwright-stealth patches
    applied. Slower than the fast path, but can render JS-built pages and
    has some chance against basic JS-based bot challenges."""
    browser = None
    p = None

    try:
        p = sync_playwright().start()

        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-NZ",
            timezone_id="Pacific/Auckland"
        )

        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        print(f"🌐 Navigating stealth browser to {url}...")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=wait_selector_timeout)
            except Exception:
                print("⏳ Expected element didn't appear in time, continuing anyway...")

        page_title = page.title()
        html = page.content()

        browser.close()
        p.stop()
        return html, page_title

    except Exception as browser_err:
        import traceback
        print(f"❌ Playwright execution error: {browser_err}")
        traceback.print_exc()
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if p:
            try:
                p.stop()
            except Exception:
                pass
        return None, None


def fetch_html_with_firefox(url: str, wait_selector: str = None, wait_selector_timeout: int = 5000):
    """
    Launches a real Firefox browser instead of Chromium. Some bot-detection
    setups are tuned specifically against Chromium's automation fingerprint
    (the CDP protocol it exposes when automated), and Firefox is driven by
    Playwright through a different, non-CDP channel — so it can occasionally
    get through where Chromium can't. This isn't a magic bypass and won't
    beat every bot-protection tier, but it's a different, legitimate signal
    profile worth trying before giving up on a site entirely.

    Note: we deliberately do NOT apply playwright-stealth's patches here.
    That library assumes a Chrome environment (it fakes `window.chrome`,
    Chrome-specific plugin lists, etc.) — injecting Chrome-only globals into
    a real Firefox page would itself be a mismatch a detector could flag.
    Instead we apply a small, Firefox-appropriate override set.
    """
    browser = None
    p = None

    try:
        p = sync_playwright().start()

        browser = p.firefox.launch(headless=True)

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
            viewport={"width": 1440, "height": 900},
            locale="en-NZ",
            timezone_id="Pacific/Auckland"
        )

        # Firefox-appropriate overrides only — no Chrome-specific globals.
        # navigator.webdriver is set to true by real Firefox under
        # automation too, so hiding it is still worthwhile here.
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-NZ', 'en'] });
        """)

        page = context.new_page()

        print(f"🦊 Navigating Firefox to {url}...")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=wait_selector_timeout)
            except Exception:
                print("⏳ Expected element didn't appear in time, continuing anyway...")

        page_title = page.title()
        html = page.content()

        browser.close()
        p.stop()
        return html, page_title

    except Exception as browser_err:
        import traceback
        print(f"❌ Firefox execution error: {browser_err}")
        traceback.print_exc()
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if p:
            try:
                p.stop()
            except Exception:
                pass
        return None, None


# =========================================================================
# MASTER ENTRY POINT — no per-domain branching needed. Paste any product
# URL and this tries the fast path first, then falls back to a real browser
# if the fast path is blocked or the page turns out to need JS rendering.
# =========================================================================

def scrape_product(url: str):
    print(f"🔎 Scraping: {url}")

    # --- Attempt 1: fast plain HTTP fetch ---
    html, status_code = fetch_html_fast(url)

    if html is not None and status_code == 200:
        title, price_raw, currency = extract_product_generic(html)
        price = clean_price(price_raw)
        if title and price is not None:
            # Successful extraction is the real proof this wasn't a block
            # page — trust it over any marker heuristic.
            print(f"✅ Fast path worked: {title.strip()} - {currency or '$'}{price}")
            return {"title": title.strip(), "price": price, "currency": currency}
        if is_bot_wall(None, html):
            print("⚠️ Fast path blocked (bot-protection page detected) — trying Chromium stealth browser...")
        else:
            print("⚠️ Fast path returned a page, but no title/price found (likely JS-rendered) — trying Chromium stealth browser...")
    else:
        print("⚠️ Fast path failed to load — trying Chromium stealth browser...")

    # --- Attempt 2: Chromium with stealth patches ---
    html, page_title = fetch_html_with_chromium_stealth(url)

    if html is not None:
        title, price_raw, currency = extract_product_generic(html)
        price = clean_price(price_raw)
        if title and price is not None:
            print(f"🎉 Chromium stealth path worked: {title.strip()} - {currency or '$'}{price}")
            return {"title": title.strip(), "price": price, "currency": currency}
        if is_bot_wall(page_title, html):
            print("⚠️ Chromium blocked (bot-protection page detected) — trying Firefox (different automation fingerprint)...")
        else:
            print("⚠️ Chromium loaded the page but found no title/price — trying Firefox...")
    else:
        print("⚠️ Chromium fetch failed entirely — trying Firefox...")

    # --- Attempt 3: Firefox as a last resort ---
    html, page_title = fetch_html_with_firefox(url)

    if html is None:
        print("❌ Firefox fetch failed entirely.")
        return None

    title, price_raw, currency = extract_product_generic(html)
    price = clean_price(price_raw)

    if title and price is not None:
        print(f"🦊 Firefox path worked: {title.strip()} - {currency or '$'}{price}")
        return {"title": title.strip(), "price": price, "currency": currency}

    if is_bot_wall(page_title, html):
        print("⚠️ Still blocked even with Firefox — this site's bot protection needs a commercial scraping API to get past reliably.")
    else:
        print("❌ Firefox loaded the page, but no title/price could be found by any method.")
    return None
    return {"title": title.strip(), "price": price, "currency": currency}