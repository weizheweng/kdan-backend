# app/models.py
from sqlalchemy import (
    Column, Integer, Float, DateTime, ForeignKey, Time, String, Enum
)
from sqlalchemy.orm import relationship
from .database import Base
import enum

# 對應 PostgreSQL 中的 day_of_week_enum: 'Mon','Tue','Wed','Thur','Fri','Sat','Sun'
class DayOfWeekEnum(str, enum.Enum):
    Mon = "Mon"
    Tue = "Tue"
    Wed = "Wed"
    Thur = "Thur"
    Fri = "Fri"
    Sat = "Sat"
    Sun = "Sun"

class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    cash_balance = Column(Float, default=0)

    # 一間藥局對多個開店時段
    opening_hours = relationship("PharmacyOpeningHours", back_populates="pharmacy", cascade="all, delete-orphan")
    # 一間藥局對多個口罩商品
    masks = relationship("Mask", back_populates="pharmacy", cascade="all, delete-orphan")

class PharmacyOpeningHours(Base):
    __tablename__ = "pharmacy_opening_hours"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    day_of_week = Column(Enum(DayOfWeekEnum, name="day_of_week_enum"), nullable=False)
    open_time = Column(Time, nullable=False)
    close_time = Column(Time, nullable=False)

    pharmacy = relationship("Pharmacy", back_populates="opening_hours")

class Mask(Base):
    __tablename__ = "masks"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    price = Column(Float, default=0)

    pharmacy = relationship("Pharmacy", back_populates="masks")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    cash_balance = Column(Float, default=0)

    purchase_histories = relationship("PurchaseHistory", back_populates="user", cascade="all, delete-orphan")

class PurchaseHistory(Base):
    __tablename__ = "purchase_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    mask_id = Column(Integer, ForeignKey("masks.id"), nullable=True)
    mask_name = Column(String(255))
    quantity = Column(Integer, default=1)
    transaction_amount = Column(Float, default=0)
    transaction_date = Column(DateTime)

    user = relationship("User", back_populates="purchase_histories")
    # 可選: relationship 到 mask / pharmacy，如需再加
