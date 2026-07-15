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
    Base.metadata.create_all(bind=engine)
    print("🏠 Database tables initialized successfully.")

def check_all_prices():
    db = SessionLocal()
    try:
        products = db.query(models.Product).all()
        
        if not products:
            print("ℹ️ No products found in database to track.")
            return

        print(f"🔄 Starting a price check cycle for {len(products)} items...")

        for product in products:
            print(f"⚡ Checking current price for: '{product.title}'...")

            try:
                scraped_data = scrape_product(product.url)

                if scraped_data:
                    new_log = models.PriceLog(
                        product_id=product.id,
                        price=scraped_data["price"]
                    )
                    db.add(new_log)
                    db.commit()
                    print(f"Logged price {scraped_data['price']} for '{product.title}'.")

                    if product.target_price and scraped_data["price"] <= product.target_price:
                        print(f"ALERT: Price dropped to {scraped_data['price']}! Target was {product.target_price}")
                else:
                    print(f"⚠️ Failed to scrape data for '{product.title}'.")

            except Exception as e:
                print(f"❌ Unexpected error processing '{product.title}': {e}")
                db.rollback()
                continue

    finally:
        db.close()

def run_pipeline():
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
    init_db()       
    run_pipeline()  
    print("\n--- Starting Multi-Product Check Run ---")
    check_all_prices()