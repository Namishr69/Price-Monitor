import re
import requests
from bs4 import BeautifulSoup

def scrape_product(url):
    # Spoof a real Mac Chrome browser header so sites don't insta-block us
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() 
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Target elements on the sandbox practice site
        title_element = soup.find("h1")
        price_element = soup.find("p", class_="price_color")
        
        if not title_element or not price_element:
            print("Error: Target elements not found on the page layout.")
            return None
            
        raw_title = title_element.get_text(strip=True)
        raw_price = price_element.get_text(strip=True)
        
        # Clean price string (e.g., "£51.77") into a clean number ("51.77")
        cleaned_price_string = re.sub(r'[^\d.]', '', raw_price)
        final_price = float(cleaned_price_string)
        
        return {
            "title": raw_title,
            "price": final_price
        }
        
    except Exception as e:
        print(f"Extraction failed: {e}")
        return None

if __name__ == "__main__":
    # Standard practice sandbox URL
    test_url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    
    print(f"Scraping sandbox link...")
    data = scrape_product(test_url)
    
    if data:
        print("\n📊 Extracted Data:")
        print(f"Title: {data['title']}")
        print(f"Price: {data['price']} (Stored as data type: {type(data['price']).__name__})")