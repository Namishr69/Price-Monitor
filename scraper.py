from bs4 import BeautifulSoup
import re
import json
from curl_cffi import requests as requests_mimic
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth


# Domains we've deliberately given up on. Their bot protection survived
# fast fetch + stealth Chromium + Firefox, so continuing to try costs real
# time every single cycle (two full browser launches, ~30-60s) for a
# product that will never succeed. Short-circuiting here means every OTHER
# product in your list gets checked faster, since we're not wasting a slot
# on a site we already know won't work. Add more domains here if you decide
# to give up on others too.
EXCLUDED_DOMAINS = {
    "woolworths.co.nz",
}

def looks_like_decoy_price(text: str) -> bool:
    """
    Grocery/retail sites are often legally required to show a unit price
    (e.g. "$0.26 / 100g") right next to the real price, for comparison
    shopping. A generic price selector can't tell these apart from the
    actual product price on its own — this filters out text that's
    clearly a unit/comparison price rather than the real one.
    """
    if not text:
        return False
    text_lower = text.lower()
    # Sites format spacing around the slash inconsistently ("$0.26/100g" vs
    # "$0.26 / 100g") — compact whitespace out before checking slash-based
    # markers so both forms match.
    text_compact = re.sub(r'\s+', '', text_lower)

    compact_markers = ['/100g', '/100ml', '/kg', '/l', '/ea', '/each', '/g', '/ml']
    phrase_markers = [
        'per 100', 'per kg', 'per litre', 'per liter', 'per each', 'per unit',
        'unit price', 'was $', 'rrp', 'compare at',
    ]

    if any(marker in text_compact for marker in compact_markers):
        return True
    if any(marker in text_lower for marker in phrase_markers):
        return True
    return False


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
        # Split-price stitcher: some sites render price as two separate
        # elements — e.g. big "$18" for dollars, small superscript "99"
        # for cents — rather than one "$18.99" text node. This finds and
        # rejoins them.
        dollars_el = soup.find(class_=re.compile(r'(?:price|product).*(?:dollars?|integer|whole)', re.I))
        cents_el = soup.find(class_=re.compile(r'(?:price|product).*(?:cents?|fraction|decimals?)', re.I))

        if dollars_el and cents_el:
            d_val = re.sub(r'[^0-9]', '', dollars_el.text)
            c_val = re.sub(r'[^0-9]', '', cents_el.text)
            if d_val:
                price = f"{d_val}.{c_val if c_val else '00'}"

        # Standard container grab-bag if it wasn't a split-price. Checks
        # EVERY candidate rather than just the first match in document
        # order, and skips anything that looks like a unit price (e.g.
        # "$0.26 / 100g", required by law on grocery sites for comparison
        # shopping) or a "was $" comparison price — otherwise a decoy like
        # that gets grabbed instead of the real price.
        if not price:
            all_candidates = (
                soup.find_all(attrs={"data-testid": re.compile("price", re.I)})
                + soup.find_all(class_=re.compile(r'price', re.I))
                + soup.find_all(class_=re.compile(r'sales', re.I))
            )
            for candidate in all_candidates:
                candidate_text = candidate.get("content") or candidate.get("price") or candidate.text.strip()
                if candidate_text and not looks_like_decoy_price(candidate_text):
                    price = candidate_text
                    break
            else:
                # Every candidate looked like a decoy — use the first one
                # anyway rather than finding nothing at all.
                if all_candidates:
                    first = all_candidates[0]
                    price = first.get("content") or first.get("price") or first.text.strip()

    # --- Method 5: visible text near the title ---
    if not price:
        body_text = soup.get_text(" ", strip=True)
        price_match = re.search(r'(?:NZ\$|AU\$|\$|NZD)\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\s*\.?\s*[0-9]{2})?)', body_text)
        if price_match:
            price = price_match.group(1)

    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.text.strip()

    return title, price, currency


def clean_price(raw_price):
    if raw_price is None:
        return None
        
    sanitized = str(raw_price).strip()
    
    # Pre-clean spacing issues
    sanitized = re.sub(r'\s*\.\s*', '.', sanitized) 
    sanitized = re.sub(r'\s+([0-9]{2})$', r'.\1', sanitized)
    sanitized = re.sub(r'\s+', '', sanitized)
    
    match = re.search(r'([0-9,]+\.?[0-9]*)', sanitized)
    if not match:
        return None
        
    value = float(match.group(1).replace(",", ""))
    
    if value > 100000 and "." not in match.group(1):
        value = value / 100.0
        
    if value == 0.0:
        return None
        
    return value


def is_bot_wall(page_title: str, html: str) -> bool:
    title_markers = ["Just a moment", "Attention Required!", "Access Denied", "Are you a human"]
    html_markers = [
        "Performing security verification",
        "challenges.cloudflare.com",   
        "_Incapsula_Resource",          
        "distil_r_captcha",             
        "px-captcha", "perimeterx",     
        "datadome",                     
        "geo.captcha-delivery.com",     
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

# The dynamic wait script injected into both browsers to confirm the
# product actually loaded (title + a price-looking element with a digit)
# before we bother capturing page content. This is faster than a blind
# fixed sleep — it returns as soon as the condition is true, rather than
# always waiting the full timeout.
SMART_WAIT_JS = """() => {
    const h1 = document.querySelector('h1');
    if (!h1 || h1.innerText.trim().length === 0) return false;

    const priceEls = document.querySelectorAll('[class*="price" i], [class*="sales" i], [data-testid*="price" i]');
    for (let el of priceEls) {
        if (el.innerText.match(/[0-9]/) || el.getAttribute('price')) return true;
    }

    return false;
}"""


def fetch_html_fast(url: str):
    try:
        response = requests_mimic.get(url, impersonate="chrome", timeout=15)
        return response.content.decode(errors="ignore"), response.status_code
    except Exception as e:
        print(f"Fast fetch failed: {e}")
        return None, None
        

def fetch_html_with_chromium_stealth(url: str, wait_selector: str = None, wait_selector_timeout: int = 5000):
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
                '--disable-http2', # FIX: Bypasses WAF HTTP/2 Protocol Errors (Forces HTTP/1.1)
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-NZ",
            timezone_id="Pacific/Auckland"
        )

        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        print(f"Navigating stealth browser to {url}...")
        
        # Wrapped the goto command to gracefully handle intentional WAF timeouts
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
        except PlaywrightTimeoutError:
            print("⏳ Chromium goto timed out (likely WAF tarpitting). Checking if page partially loaded...")
        except Exception as nav_err:
            if "net::ERR_TIMED_OUT" in str(nav_err):
                print("⏳ Chromium network timed out.")
            else:
                raise nav_err
        
        # Smart Wait: Won't trigger until H1 and Price actually exist
        try:
            page.wait_for_function(SMART_WAIT_JS, timeout=8000)
        except:
            pass 

        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=wait_selector_timeout)
            except Exception:
                pass

        page_title = page.title()
        html = page.content()

        browser.close()
        p.stop()
        return html, page_title

    except Exception as browser_err:
        print(f"Playwright execution error: {browser_err}")
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

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-NZ', 'en'] });
        """)

        page = context.new_page()

        print(f"Navigating Firefox to {url}...")
        
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
        except PlaywrightTimeoutError:
            print("⏳ Firefox goto timed out. Checking if page partially loaded...")
        except Exception as nav_err:
            if "net::ERR_TIMED_OUT" in str(nav_err):
                print("⏳ Firefox network timed out.")
            else:
                raise nav_err
        
        try:
            page.wait_for_function(SMART_WAIT_JS, timeout=8000)
        except:
            pass

        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=wait_selector_timeout)
            except Exception:
                pass

        page_title = page.title()
        html = page.content()

        browser.close()
        p.stop()
        return html, page_title

    except Exception as browser_err:
        print(f"Firefox execution error: {browser_err}")
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

def scrape_product(url: str):
    # Stripping out whitespace and stray quotes that cause local 400 Bad Request errors
    url = url.strip(' "\'')

    if any(domain in url for domain in EXCLUDED_DOMAINS):
        print(f"⏭️ Skipping {url} — this domain is in EXCLUDED_DOMAINS (given up on its bot protection).")
        return None

    print(f"Scraping: {url}")

    # --- Attempt 1: fast plain HTTP fetch ---
    html, status_code = fetch_html_fast(url)

    if html is not None and status_code == 200:
        title, price_raw, currency = extract_product_generic(html)
        price = clean_price(price_raw)
        if title and price is not None:
            print(f"Fast path worked: {title.strip()} - {currency or '$'}{price}")
            return {"title": title.strip(), "price": price, "currency": currency}
        if is_bot_wall(None, html):
            print("Fast path blocked (bot-protection page detected) — trying Chromium stealth browser...")
        else:
            print("Fast path returned a page, but no title/price found (likely JS-rendered) — trying Chromium stealth browser...")
    else:
        print("Fast path failed to load — trying Chromium stealth browser...")

    # --- Attempt 2: Chromium with stealth patches ---
    html, page_title = fetch_html_with_chromium_stealth(url)

    if html is not None:
        title, price_raw, currency = extract_product_generic(html)
        price = clean_price(price_raw)
        if title and price is not None:
            print(f"Chromium stealth path worked: {title.strip()} - {currency or '$'}{price}")
            return {"title": title.strip(), "price": price, "currency": currency}
        if is_bot_wall(page_title, html):
            print("Chromium blocked (bot-protection page detected) — trying Firefox (different automation fingerprint)...")
        else:
            print("Chromium loaded the page but found no title/price — trying Firefox...")
    else:
        print("Chromium fetch failed entirely — trying Firefox...")

    # --- Attempt 3: Firefox as a last resort ---
    html, page_title = fetch_html_with_firefox(url)

    if html is None:
        print("Firefox fetch failed entirely.")
        return None

    title, price_raw, currency = extract_product_generic(html)
    price = clean_price(price_raw)

    if title and price is not None:
        print(f"Firefox path worked: {title.strip()} - {currency or '$'}{price}")
        return {"title": title.strip(), "price": price, "currency": currency}

    if is_bot_wall(page_title, html):
        print("Still blocked even with Firefox — this site's bot protection needs a commercial scraping API to get past reliably.")
    else:
        print("Firefox loaded the page, but no title/price could be found by any method.")
    return None