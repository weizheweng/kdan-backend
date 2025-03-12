# app/routers/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.database import get_db
from app.models import User, Pharmacy, Mask, PurchaseHistory
from app.schemas import (
    User as UserSchema,
    PurchaseHistory as PurchaseHistorySchema,
    PurchaseHistoryBase,
    TopSpendersResponse,
    TransactionSummary
)

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/", response_model=List[UserSchema])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@router.get("/{user_id}/purchases", response_model=List[PurchaseHistorySchema])
def get_user_purchases(user_id: int, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u.purchase_histories

@router.post("/{user_id}/purchase")
def purchase_mask(user_id: int, body: PurchaseHistoryBase, db: Session = Depends(get_db)):
    """
    Process a user purchases a mask from a pharmacy (atomic).
    - Check user balance
    - Check mask / pharmacy
    - user.cash_balance -= (transaction_amount)
    - pharmacy.cash_balance += (transaction_amount)
    - Insert purchase_histories
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pharmacy = db.query(Pharmacy).filter(Pharmacy.id == body.pharmacy_id).first()
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")

    # 如果帶了 mask_id，就檢查對應 mask
    selected_mask = None
    if body.mask_id:
        selected_mask = db.query(Mask).filter(Mask.id == body.mask_id, Mask.pharmacy_id == pharmacy.id).first()
        if not selected_mask:
            raise HTTPException(status_code=404, detail="Mask not found in this pharmacy")

    # 檢查餘額
    total_price = body.transaction_amount
    if user.cash_balance < total_price:
        raise HTTPException(status_code=400, detail="Insufficient user balance")

    # 在同一 transaction 中更新
    user.cash_balance -= total_price
    pharmacy.cash_balance += total_price

    new_purchase = PurchaseHistory(
        user_id=user.id,
        pharmacy_id=pharmacy.id,
        mask_id=body.mask_id,
        mask_name=body.mask_name,
        quantity=body.quantity,
        transaction_amount=total_price,
        transaction_date=body.transaction_date
    )
    db.add(new_purchase)
    db.commit()
    db.refresh(user)
    db.refresh(pharmacy)
    db.refresh(new_purchase)

    return {"message": "Purchase successful", "purchase_id": new_purchase.id}

@router.get("/top_spenders", response_model=List[TopSpendersResponse])
def top_spenders(start_date: datetime, end_date: datetime, top_x: int, db: Session = Depends(get_db)):
    """
    The top x users by total transaction amount of masks within a date range.
    e.g. GET /users/top_spenders?start_date=2021-01-01T00:00:00&end_date=2021-01-31T23:59:59&top_x=5
    """
    from sqlalchemy import func
    res = (db.query(
                PurchaseHistory.user_id,
                func.sum(PurchaseHistory.transaction_amount).label("total_spent")
            )
            .filter(PurchaseHistory.transaction_date >= start_date,
                    PurchaseHistory.transaction_date <= end_date)
            .group_by(PurchaseHistory.user_id)
            .order_by(func.sum(PurchaseHistory.transaction_amount).desc())
            .limit(top_x)
            .all()
          )
    # 取得 user name
    results = []
    for row in res:
        user_obj = db.query(User).filter(User.id == row.user_id).first()
        results.append(TopSpendersResponse(
            user_id=row.user_id,
            user_name=user_obj.name if user_obj else "",
            total_spent=row.total_spent
        ))
    return results

@router.get("/transactions/summary", response_model=TransactionSummary)
def transaction_summary(start_date: datetime, end_date: datetime, db: Session = Depends(get_db)):
    """
    The total amount of masks and dollar value of transactions within a date range.
    - total_masks = sum of quantity
    - total_dollar = sum of transaction_amount
    """
    from sqlalchemy import func
    row = (db.query(
               func.sum(PurchaseHistory.quantity).label("total_masks"),
               func.sum(PurchaseHistory.transaction_amount).label("total_dollar")
           )
           .filter(PurchaseHistory.transaction_date >= start_date,
                   PurchaseHistory.transaction_date <= end_date)
           .first()
          )
    total_masks = row[0] if row[0] else 0
    total_dollar = row[1] if row[1] else 0
    return TransactionSummary(
        total_masks=int(total_masks),
        total_dollar=float(total_dollar)
    )
