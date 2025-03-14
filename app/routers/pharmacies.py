# app/routers/pharmacies.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import time
from app.database import get_db
from app.models import Pharmacy, PharmacyOpeningHours, Mask
from app.schemas import Pharmacy as PharmacySchema, Mask as MaskSchema
from app.utils.time_helper import is_open_now

router = APIRouter(prefix="/pharmacies", tags=["Pharmacies"])

@router.get("/open", response_model=List[PharmacySchema])
def get_open_pharmacies(day_of_week: Optional[str], time_str: Optional[str], db: Session = Depends(get_db)):
    """
    List all pharmacies open at a specific time and on a day of week if requested.
    e.g. GET /pharmacies/open?day_of_week=Thur&time_str=14:00
    若兩個參數都沒傳，回傳所有藥局。
    """
    query = db.query(Pharmacy)
    pharmacies = query.all()
    if not day_of_week or not time_str:
        return pharmacies  # 無參數則全部

    # 轉換 time_str -> time
    hour_min = time_str.split(":")
    check_time = time(int(hour_min[0]), int(hour_min[1]) if len(hour_min) > 1 else 0)

    result = []
    for ph in pharmacies:
        ohs = ph.opening_hours
        is_open = False
        for oh in ohs:
            if oh.day_of_week.value == day_of_week:
                if is_open_now(oh.open_time, oh.close_time, check_time):
                    is_open = True
                    break
        if is_open:
            result.append(ph)
    return result

@router.get("/{pharmacy_id}/masks", response_model=List[MaskSchema])
def list_masks_of_pharmacy(
    pharmacy_id: int,
    sort_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all masks sold by a given pharmacy, sorted by mask name or price.
    e.g. GET /pharmacies/5/masks?sort_by=price
    """
    q = db.query(Mask).filter(Mask.pharmacy_id == pharmacy_id)
    if sort_by == "name":
        q = q.order_by(Mask.name)
    elif sort_by == "price":
        q = q.order_by(Mask.price)
    return q.all()

@router.get("/filter", response_model=List[PharmacySchema])
def filter_pharmacies_mask_count(
    count_op: str,
    count_val: int,
    price_min: float,
    price_max: float,
    db: Session = Depends(get_db)
):
    """
    List all pharmacies with more or less than x mask products within a price range.
    e.g. GET /pharmacies/filter?count_op=gt&count_val=3&price_min=10&price_max=50
    """
    # 先找出在 price_min~price_max 之間的 masks
    subq = db.query(Mask.pharmacy_id).filter(Mask.price.between(price_min, price_max))

    # group by pharmacy_id, 並計算符合該區間的口罩數量
    from sqlalchemy import func
    subq_count = (db.query(Mask.pharmacy_id, func.count(Mask.id).label("cnt"))
                  .filter(Mask.price.between(price_min, price_max))
                  .group_by(Mask.pharmacy_id)
                  ).subquery()

    # 再與 pharmacies join
    query = db.query(Pharmacy).join(subq_count, subq_count.c.pharmacy_id == Pharmacy.id)

    # 篩選 count_op
    if count_op == "gt":
        query = query.filter(subq_count.c.cnt > count_val)
    elif count_op == "lt":
        query = query.filter(subq_count.c.cnt < count_val)
    else:
        raise HTTPException(status_code=400, detail="count_op must be 'gt' or 'lt'")

    return query.all()


@router.get("/all_masks", response_model=List[MaskSchema])
def list_all_masks(db: Session = Depends(get_db)):
    """
    撈全部藥局的口罩 (即 masks 表內所有資料)
    """
    return db.query(Mask).all()