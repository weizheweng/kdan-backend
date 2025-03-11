from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import enum

# 這裡也可定義與 DB 相同的列舉，若要做 request/response 驗證。
class DayOfWeek(str, enum.Enum):
    Mon = "Mon"
    Tue = "Tue"
    Wed = "Wed"
    Thur = "Thur"
    Fri = "Fri"
    Sat = "Sat"
    Sun = "Sun"

# ============ Pharmacy Schemas ==============
class PharmacyBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    cash_balance: float = 0

class PharmacyCreate(PharmacyBase):
    pass

class Pharmacy(PharmacyBase):
    id: int
    class Config:
        orm_mode = True

# ============ PharmacyOpeningHours ==============
class PharmacyOpeningHoursBase(BaseModel):
    day_of_week: DayOfWeek
    open_time: str  # 以 'HH:MM:SS' 表示
    close_time: str

class PharmacyOpeningHoursCreate(PharmacyOpeningHoursBase):
    pass

class PharmacyOpeningHours(PharmacyOpeningHoursBase):
    id: int
    pharmacy_id: int
    class Config:
        orm_mode = True

# ============ User Schemas ==============
class UserBase(BaseModel):
    name: str
    cash_balance: float = 0

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    class Config:
        orm_mode = True

# ============ PurchaseHistory ==============
class PurchaseHistoryBase(BaseModel):
    pharmacy_id: int
    mask_name: str
    transaction_amount: float
    transaction_date: datetime

class PurchaseHistoryCreate(PurchaseHistoryBase):
    pass

class PurchaseHistory(PurchaseHistoryBase):
    id: int
    user_id: int
    class Config:
        orm_mode = True