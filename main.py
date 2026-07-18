from sqlalchemy.orm.exc import ObjectDeletedError
import traceback

from models import SessionLocal, engine, Base
from models import Product, PriceLog
from scraper import scrape_product

# Create database tables
Base.metadata.create_all(bind=engine)

def check_all_prices():
    """
    Background job to scrape updated prices for all products. Called by
    the scheduler set up in api.py — this file has no FastAPI app of its
    own (it used to, but that app/scheduler pair was never actually served
    by anything and was dead code; worse, it was a latent footgun since
    accidentally running `uvicorn main:app` instead of `uvicorn api:app`
    would have started a second, independent scheduler racing the real one).
    """
    db = SessionLocal()
    try:
        products = db.query(Product).all()
        print(f"Starting a price check cycle for {len(products)} items...")
        
        for product in products:
            try:
                # Start the try block immediately so accessing deleted attributes won't crash
                print(f"Checking current price for: '{product.title}'...")
                
                scraped_data = scrape_product(product.url)
                
                if scraped_data and scraped_data.get("price"):
                    new_price = scraped_data["price"]
                    
                    history_entry = PriceLog(
                        product_id=product.id,
                        price=new_price
                    )
                    db.add(history_entry)
                    db.commit()
                    
                    print(f"Logged price {new_price} for '{product.title}'.")
                else:
                    print(f"Failed to scrape data for '{product.title}'.")
                    
            except ObjectDeletedError:
                # If a user deletes the product from the UI while the background 
                # scraper is processing it, this cleanly skips it instead of crashing.
                print("⚠️ Product was deleted from the database mid-scrape. Skipping.")
                db.rollback()
                continue
            except Exception as e:
                print(f"⚠️ Unexpected error checking {product.url}: {e}")
                traceback.print_exc()
                db.rollback()
                continue

    finally:
        db.close()