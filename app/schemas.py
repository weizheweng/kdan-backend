# app/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, time
import enum

class DayOfWeek(str, enum.Enum):
    Mon = "Mon"
    Tue = "Tue"
    Wed = "Wed"
    Thur = "Thur"
    Fri = "Fri"
    Sat = "Sat"
    Sun = "Sun"

# ---- Pharmacy & Opening Hours ----
class PharmacyBase(BaseModel):
    name: str
    cash_balance: float = 0

class Pharmacy(PharmacyBase):
    id: int
    class Config:
        orm_mode = True

class PharmacyOpeningHoursBase(BaseModel):
    day_of_week: DayOfWeek
    open_time: time
    close_time: time

class PharmacyOpeningHours(PharmacyOpeningHoursBase):
    id: int
    pharmacy_id: int
    class Config:
        orm_mode = True

# ---- Mask ----
class MaskBase(BaseModel):
    name: str
    price: float

class Mask(MaskBase):
    id: int
    pharmacy_id: int
    class Config:
        orm_mode = True

# ---- User & PurchaseHistory ----
class UserBase(BaseModel):
    name: str
    cash_balance: float = 0

class User(UserBase):
    id: int
    class Config:
        orm_mode = True

class PurchaseHistoryBase(BaseModel):
    pharmacy_id: int
    mask_id: Optional[int] = None
    mask_name: Optional[str] = None
    quantity: int = 1
    transaction_amount: float
    transaction_date: datetime

class PurchaseHistory(PurchaseHistoryBase):
    id: int
    user_id: int
    class Config:
        orm_mode = True

# ---- Special Query schemas ----
class DateRange(BaseModel):
    start_date: datetime
    end_date: datetime

class TopSpendersResponse(BaseModel):
    user_id: int
    user_name: str
    total_spent: float

class TransactionSummary(BaseModel):
    total_masks: int
    total_dollar: float
