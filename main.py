from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, User, Product, PriceLog
from scraper import scrape_product

# 1. Connect to Database (Creates a local 'wishlist.db' file)
# To switch to PostgreSQL later, you'd just change this line to:
# DATABASE_URL = "postgresql://user:password@localhost:5432/dbname"
DATABASE_URL = "sqlite:///wishlist.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("🏠 Database tables initialized successfully.")

def run_pipeline():
    # Instantiate a database session
    db = SessionLocal()
    
    try:
        # 2. Ensure a demo user exists so we have someone to attach the product to
        demo_user = db.query(User).filter_by(email="namish@example.com").first()
        if not demo_user:
            demo_user = User(email="namish@example.com")
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)
            print(f"👤 Created demo user: {demo_user.email}")

        # 3. Define the product url to track
        target_url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        
        # Check if we are already tracking this product for this user
        product = db.query(Product).filter_by(user_id=demo_user.id, url=target_url).first()
        
        # 4. If it's a new product, scrape it to get details and insert into 'products' table
        if not product:
            print("🔍 New product detected. Fetching metadata...")
            scraped_data = scrape_product(target_url)
            
            if scraped_data:
                product = Product(
                    user_id=demo_user.id,
                    title=scraped_data["title"],
                    url=target_url,
                    target_price=45.00  # Example alert threshold set by user
                )
                db.add(product)
                db.commit()
                db.refresh(product)
                print(f"📦 Successfully added product: '{product.title}' to tracking list.")
            else:
                print("❌ Initial scrape failed. Aborting pipeline.")
                return

        # 5. Simulate a Price Check Operation (This runs every time your tracker loops)
        print(f"⚡ Checking current price for: '{product.title}'...")
        current_data = scrape_product(product.url)
        
        if current_data:
            # Create a history entry with the timestamp
            new_log = PriceLog(
                product_id=product.id,
                price=current_data["price"]
            )
            db.add(new_log)
            db.commit()
            print(f"💾 Logged price {new_log.price} at {new_log.checked_at}")
            
            # 6. Basic Alert Check Logic
            if new_log.price <= product.target_price:
                print(f"🚨 ALERT: Price dropped to {new_log.price}! Target was {product.target_price}")
            else:
                print(f"ℹ️ Current price ({new_log.price}) is still above target ({product.target_price}).")
                
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    run_pipeline()