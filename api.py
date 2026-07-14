import os
from typing import List
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

# Import APScheduler elements to manage our background loop
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

import models
import schemas
from scraper import scrape_product

# Import both the DB config and the sweep engine directly from main
from main import SessionLocal, engine, check_all_prices

# Initialize database tables using the active engine mapping
models.Base.metadata.create_all(bind=engine)

# AUTOMATED BACKGROUND HEARTBEAT
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spin up the scheduler
    scheduler = BackgroundScheduler()
    
    # 1. Runs IMMEDIATELY on startup (using datetime.now())
    # 2. Runs every 10 seconds after that for rapid visual testing!
    from datetime import datetime
    scheduler.add_job(
        check_all_prices, 
        'interval', 
        seconds=10, 
        next_run_time=datetime.now() 
    )
    
    scheduler.start()
    print("Automated Price Checking Engine Started (Interval: 10s, Initial Run: Instant)")
    
    yield
    
    scheduler.shutdown()
    print("Automated Price Checking Engine Stopped")

# Pass the lifespan manager directly into FastAPI
app = FastAPI(title="Price Monitor API Dashboard", version="1.0.0", lifespan=lifespan)

# Security Gateway: Allows frontend cross-origin data requests across ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Session Dependency Injection
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =====================================================================
# BACKEND API DATA ROUTES
# =====================================================================

@app.get("/products", response_model=List[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    """Fetch all tracked products straight from SQLite database rows."""
    return db.query(models.Product).all()

# FIXED: Added the missing @app. decorator
@app.post("/products")
def add_product(product_in: schemas.ProductCreate, db: Session = Depends(get_db)):
    # 1. Run the live scraper on the new URL
    scraped_data = scrape_product(product_in.url)
    
    if not scraped_data:
        raise HTTPException(status_code=400, detail="Could not scrape product details from this website.")
    
    # 2. Create the master product profile
    new_product = models.Product(
        user_id=1,  # Fallback ID to satisfy our database constraints
        title=scraped_data["title"],
        url=product_in.url
    )
    db.add(new_product)
    db.flush()  
    
    # 3. IMMEDIATELY create the very first price log for the chart!
    initial_log = models.PriceLog(
        product_id=new_product.id,
        price=scraped_data["price"]
    )
    db.add(initial_log)
    
    db.commit()
    db.refresh(new_product)
    
    return new_product

@app.get("/products/{product_id}/history", response_model=List[schemas.PriceLogResponse])
def get_product_history(product_id: int, db: Session = Depends(get_db)):
    """Chronologically organizes the historical tracking records for a specific product ID."""
    return db.query(models.PriceLog).filter(models.PriceLog.product_id == product_id).order_by(models.PriceLog.checked_at.asc()).all()

# FIXED: Moved the delete endpoint ABOVE the static mount block
@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Deletes a specific product and all its cascade dependencies (price logs)."""
    # 1. Look for the product in our database
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    
    # 2. Delete it (This cascades automatically and deletes its price_logs!)
    db.delete(product)
    db.commit()
    
    return {"message": f"Successfully deleted product {product_id}."}

# STATIC UI DASHBOARD HOSTING MOUNT
current_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=current_dir, html=True), name="static")