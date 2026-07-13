import requests
from bs4 import BeautifulSoup
import re

def scrape_product(url: str):
    # Enhanced browser headers to look like a legitimate MacOS user
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive"
    }
    
    try:
        # We add a session wrapper to maintain cookies, which helps bypass bot walls
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # --- JB HI FI PARSING ENGINE ---
        if "jbhifi.co.nz" in url:
            # Noel Leeming stores product titles inside an h1 with a specific class or property
            title_element = soup.find("h1", {"class": "product-title"}) or soup.find("h1")
            
            # They format price inside a specific product pricing container
            price_element = soup.find("span", {"class": "price-tag"}) or soup.find("span", {"class": "sales"})
            
            if not title_element or not price_element:
                print("⚠️ Successfully bypassed 403, but HTML selectors didn't find the elements.")
                return None
                
            title = title_element.text.strip()
            price_text = price_element.text.strip()
            
            # Clean out any dollar signs, commas, or whitespace (e.g., $1,249.00 -> 1249.00)
            price = float(re.sub(r'[^\d.]', '', price_text))
            
            return {"title": title, "price": price}
            
        # Fallback to keep your working books tracking engine active
        elif "books.toscrape.com" in url:
            title = soup.find("h1").text.strip()
            price_text = soup.find("p", class_="price_color").text.strip()
            price = float(re.sub(r'[^\d.]', '', price_text))
            return {"title": title, "price": price}
            
        else:
            print(f"⚠️ Unsupported Domain: {url}")
            return None
            
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return None