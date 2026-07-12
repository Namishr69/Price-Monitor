from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
from scraper import scrape_product

app = FastAPI(title="Price Monitor API Dashboard", version="1.0.0")

# Enable CORS so your future frontend dashboard can communicate with it cleanly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get a clean database session per request
def get_db():
    db = models.SessionLocal() if hasattr(models, 'SessionLocal') else None
    if not db:
        # Fallback inline instantiation matching your main.py layout
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        engine = create_engine("sqlite:///wishlist.db", connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# HARDCODED DEMO USER ID FOR DEVELOPMENT (Matches main.py profile setup)
DEMO_USER_ID = 1

@app.get("/products", response_model=List[schemas.ProductResponse])
def get_tracked_products(db: Session = Depends(get_db)):
    """Fetch all products currently being monitored for the user."""
    products = db.query(models.Product).filter(models.Product.user_id == DEMO_USER_ID).all()
    return products

@app.post("/products", response_model=schemas.ProductResponse)
def add_new_product(payload: schemas.ProductCreate, db: Session = Depends(get_db)):
    """Pass a new URL to automatically scrape details and add it to the tracking matrix."""
    # Check if user is already tracking this exact URL
    existing_product = db.query(models.Product).filter(
        models.Product.user_id == DEMO_USER_ID, 
        models.Product.url == payload.url
    ).first()
    
    if existing_product:
        raise HTTPException(status_code=400, detail="You are already tracking this product URL.")
        
    # Scrape the item details live
    print(f"🌐 API Pipeline: Live scraping target url -> {payload.url}")
    scraped_data = scrape_product(payload.url)
    
    if not scraped_data:
        raise HTTPException(status_code=422, detail="Failed to scrape or extract valid pricing metadata from this URL.")
        
    # Commit the newly registered product structure to storage
    new_product = models.Product(
        user_id=DEMO_USER_ID,
        title=scraped_data["title"],
        url=payload.url,
        target_price=payload.target_price
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    # Save the initial historical log seed row right away
    initial_log = models.PriceLog(product_id=new_product.id, price=scraped_data["price"])
    db.add(initial_log)
    db.commit()
    
    return new_product

@app.get("/products/{product_id}/history", response_model=List[schemas.PriceLogResponse])
def get_product_price_history(product_id: int, db: Session = Depends(get_db)):
    """Fetch the chronological price timeline trend logs for graphing libraries."""
    product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.user_id == DEMO_USER_ID).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product tracking ledger not found.")
        
    logs = db.query(models.PriceLog).filter(models.PriceLog.product_id == product_id).order_by(models.PriceLog.checked_at.asc()).all()
    return logs