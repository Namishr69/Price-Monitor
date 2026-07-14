import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, User, Product, PriceLog
from scraper import scrape_product
import models

DATABASE_URL = "sqlite:///wishlist.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("🏠 Database tables initialized successfully.")

def check_all_prices():
    """Loops through and checks prices for EVERY product saved in the DB."""
    db = SessionLocal()
    try:
        # Fetch every product stored in your SQLite database
        products = db.query(models.Product).all()
        
        if not products:
            print("ℹ️ No products found in database to track.")
            return

        print(f"🔄 Starting a price check cycle for {len(products)} items...")

        for product in products:
            print(f"⚡ Checking current price for: '{product.title}'...")
            
            # Scrape the current product's active URL
            scraped_data = scrape_product(product.url)
            
            if scraped_data:
                # Add a new historical log entry for this specific product
                new_log = models.PriceLog(
                    product_id=product.id,
                    price=scraped_data["price"]
                )
                db.add(new_log)
                db.commit()
                print(f"Logged price {scraped_data['price']} for '{product.title}'.")
                
                # Basic Alert Check Logic if a target price exists
                if product.target_price and scraped_data["price"] <= product.target_price:
                    print(f"ALERT: Price dropped to {scraped_data['price']}! Target was {product.target_price}")
            else:
                print(f"⚠️ Failed to scrape data for '{product.title}'.")
                
    finally:
        db.close()

def run_pipeline():
    """Ensures a demo user and a starting product exist in the system."""
    db = SessionLocal()
    try:
        demo_user = db.query(User).filter_by(email="namish@example.com").first()
        if not demo_user:
            demo_user = User(email="namish@example.com")
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)
            print(f"👤 Created demo user: {demo_user.email}")

        target_url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        product = db.query(Product).filter_by(user_id=demo_user.id, url=target_url).first()
        
        if not product:
            print("🔍 New product detected. Fetching metadata...")
            scraped_data = scrape_product(target_url)
            
            if scraped_data:
                product = Product(
                    user_id=demo_user.id,
                    title=scraped_data["title"],
                    url=target_url,
                    target_price=45.00
                )
                db.add(product)
                db.commit()
                db.refresh(product)
                print(f"📦 Successfully added product: '{product.title}' to tracking list.")
                
    finally:
        db.close()


if __name__ == "__main__":
    init_db()       # 1. Spin up DB tables
    run_pipeline()  # 2. Seed default data if empty
    print("\n--- Starting Multi-Product Check Run ---")
    check_all_prices() # 3. Run the live scraper loop over everything!