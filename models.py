import datetime
from typing import List
from sqlalchemy import ForeignKey, String, DateTime, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Base class for all database models
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    # Relationship: A user can have many tracked products
    products: Mapped[List["Product"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Product(Base):
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="products")
    price_logs: Mapped[List["PriceLog"]] = relationship(back_populates="product", cascade="all, delete-orphan")

class PriceLog(Base):
    __tablename__ = "price_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    checked_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationship
    product: Mapped["Product"] = relationship(back_populates="price_logs")