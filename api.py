import os
from typing import List
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import models
import schemas
from scraper import scrape_product

# Import the working database configurations directly from main
from main import SessionLocal, engine

# Initialize database tables using the active engine mapping
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Price Monitor API Dashboard", version="1.0.0")

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
    products = db.query(models.Product).all()
    return products

@app.post("/products", response_model=schemas.ProductResponse)
def add_product(product_in: schemas.ProductCreate, db: Session = Depends(get_db)):
    """Accepts a URL string, executes the live web scraper engine, 
    persists records to storage, and logs initial pricing metadata."""
    existing_product = db.query(models.Product).filter(models.Product.url == product_in.url).first()
    if existing_product:
        return existing_product

    # Trigger scraper framework
    scraped_data = scrape_product(product_in.url)
    if not scraped_data:
        raise HTTPException(status_code=400, detail="Could not parse or scrape metadata out of this URL target.")

    # Create master product profile
    new_product = models.Product(
        user_id=0, 
        title=scraped_data["title"],
        url=product_in.url
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    # Log initial historical price record entry
    initial_log = models.PriceLog(
        product_id=new_product.id,
        price=scraped_data["price"]
    )
    db.add(initial_log)
    db.commit()

    return new_product

@app.get("/products/{product_id}/history", response_model=List[schemas.PriceLogResponse])
def get_product_history(product_id: int, db: Session = Depends(get_db)):
    """Chronologically organizes the historical tracking records for a specific product ID."""
    logs = db.query(models.PriceLog).filter(models.PriceLog.product_id == product_id).order_by(models.PriceLog.checked_at.asc()).all()
    return logs

# =====================================================================
# STATIC UI DASHBOARD HOSTING MOUNT (MUST REMAIN AT ABSOLUTE BOTTOM)
# =====================================================================

# Force runtime context lookup to dynamically target index.html inside the workspace directory
current_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=current_dir, html=True), name="static")