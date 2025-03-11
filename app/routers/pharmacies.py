from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import time
from app.database import get_db
from app.models import Pharmacy, PharmacyOpeningHours
from app.schemas import Pharmacy as PharmacySchema
from app.schemas import PharmacyOpeningHours as PharmacyOpeningHoursSchema
from app.utils.time_helper import is_open_at

router = APIRouter(prefix="/pharmacies", tags=["Pharmacies"])

@router.get("/", response_model=List[PharmacySchema])
def list_pharmacies(db: Session = Depends(get_db)):
    """
    列出所有藥局
    """
    return db.query(Pharmacy).all()

@router.get("/open", response_model=List[PharmacySchema])
def get_open_pharmacies(
    day_of_week: str,
    time_str: str,
    db: Session = Depends(get_db)
):
    """
    篩選在指定 day_of_week + time_str 有營業的藥局
    例如 GET /pharmacies/open?day_of_week=Thur&time_str=14:00
    """
    pharmacies = db.query(Pharmacy).all()
    open_pharmacies = []
    # 把 time_str => time object
    hour_min = time_str.split(":")
    check_time = time(int(hour_min[0]), int(hour_min[1]) if len(hour_min) > 1 else 0)

    for ph in pharmacies:
        # 取出該 pharmacy 所有營業時段
        ohours = ph.opening_hours  # list[PharmacyOpeningHours]
        for oh in ohours:
            if oh.day_of_week.value == day_of_week:
                # 檢查 check_time 是否落在 open_time 與 close_time 之間
                # 也可呼叫自己寫好的 is_open_at( oh, check_time )
                if oh.open_time <= check_time <= oh.close_time:
                    open_pharmacies.append(ph)
                    break
    return open_pharmacies

@router.get("/{pharmacy_id}", response_model=PharmacySchema)
def get_pharmacy(pharmacy_id: int, db: Session = Depends(get_db)):
    ph = db.query(Pharmacy).filter(Pharmacy.id == pharmacy_id).first()
    if not ph:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    return ph

@router.get("/{pharmacy_id}/opening_hours", response_model=List[PharmacyOpeningHoursSchema])
def list_opening_hours(pharmacy_id: int, db: Session = Depends(get_db)):
    ohours = db.query(PharmacyOpeningHours).filter(PharmacyOpeningHours.pharmacy_id == pharmacy_id).all()
    return ohours