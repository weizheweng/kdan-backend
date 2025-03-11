from sqlalchemy import (
    Column, Integer, String, Time, ForeignKey, Enum, Float, DateTime
)
from sqlalchemy.orm import relationship
from .database import Base
import enum

# 若 ENUM 已在 DB 裡定義 'Thur'，Python Enum 也要對應
class DayOfWeekEnum(str, enum.Enum):
    Mon = "Mon"
    Tue = "Tue"
    Wed = "Wed"
    Thur = "Thur"  # 注意這裡用 Thur
    Fri = "Fri"
    Sat = "Sat"
    Sun = "Sun"

class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    address = Column(String(255))
    phone = Column(String(50))
    cash_balance = Column(Float, default=0)

    # relationship: 一間藥局對多個營業時間
    opening_hours = relationship("PharmacyOpeningHours", back_populates="pharmacy", cascade="all, delete-orphan")

class PharmacyOpeningHours(Base):
    __tablename__ = "pharmacy_opening_hours"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    day_of_week = Column(Enum(DayOfWeekEnum, name="day_of_week_enum"), nullable=False)
    open_time = Column(Time, nullable=False)
    close_time = Column(Time, nullable=False)

    pharmacy = relationship("Pharmacy", back_populates="opening_hours")

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
    mask_name = Column(String(255))
    transaction_amount = Column(Float, default=0)
    transaction_date = Column(DateTime)

    user = relationship("User", back_populates="purchase_histories")
    # 若需要可再 relationship 回 pharmacies（多對多）或一對多