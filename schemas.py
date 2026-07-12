from pydantic import BaseModel, EmailStr, HttpUrl
from typing import List, Optional
from datetime import datetime

# Base Log Schemas
class PriceLogResponse(BaseModel):
    id: int
    price: float
    checked_at: datetime

    class Config:
        from_attributes = True

# Base Product Schemas
class ProductBase(BaseModel):
    url: str

class ProductCreate(ProductBase):
    target_price: Optional[float] = None

class ProductResponse(BaseModel):
    id: int
    user_id: int
    title: str
    url: str
    target_price: Optional[float]

    class Config:
        from_attributes = True