import os
import datetime
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

# Import DB config and loop engine from main.py
from main import SessionLocal, engine, check_all_prices

# Initialize database tables
models.Base.metadata.create_all(bind=engine)

# AUTOMATED BACKGROUND HEARTBEAT
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    
    # Schedule to run immediately on startup and every 4 hours after
    scheduler.add_job(
        check_all_prices, 
        'interval', 
        hours=4, 
        next_run_time=datetime.datetime.now() 
    )
    
    scheduler.start()
    print("Automated Price Checking Engine Started (Interval: 4 hours)")
    
    yield
    
    scheduler.shutdown()
    print("Automated Price Checking Engine Stopped")

app = FastAPI(title="Price Monitor API Dashboard", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/products", response_model=List[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    return db.query(models.Product).all()

@app.post("/products")
def add_product(product_in: schemas.ProductCreate, db: Session = Depends(get_db)):
    scraped_data = scrape_product(product_in.url)
    
    if not scraped_data:
        raise HTTPException(status_code=400, detail="Could not scrape product details from this website.")
    
    new_product = models.Product(
        user_id=1, 
        title=scraped_data["title"],
        url=product_in.url
    )
    db.add(new_product)
    db.flush()  
    
    # FIX: Create TWO initial price logs offset by 1 second so Chart.js renders a line.
    now = datetime.datetime.utcnow()
    
    initial_log_1 = models.PriceLog(
        product_id=new_product.id,
        price=scraped_data["price"],
        checked_at=now - datetime.timedelta(seconds=1)
    )
    
    initial_log_2 = models.PriceLog(
        product_id=new_product.id,
        price=scraped_data["price"],
        checked_at=now
    )
    
    db.add_all([initial_log_1, initial_log_2])
    db.commit()
    db.refresh(new_product)
    
    return new_product

@app.get("/products/{product_id}/history", response_model=List[schemas.PriceLogResponse])
def get_product_history(product_id: int, limit: int = 200, db: Session = Depends(get_db)):
    logs = (
        db.query(models.PriceLog)
        .filter(models.PriceLog.product_id == product_id)
        .order_by(models.PriceLog.checked_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(logs))

@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    
    db.delete(product)
    db.commit()
    return {"message": f"Successfully deleted product {product_id}."}

current_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=current_dir, html=True), name="static")