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
def purchase_masks(
    user_id: int,
    items: List[PurchaseHistoryBase],
    db: Session = Depends(get_db)
):
    """
    接收多筆購買資料，一次性處理：
    [
      {
        "pharmacy_id": 3,
        "mask_id": 10,
        "mask_name": "MaskT (green) (10 per pack)",
        "quantity": 2,
        "transaction_amount": 80.0,
        "transaction_date": "2023-01-01T10:00:00"
      },
      {
        "pharmacy_id": 3,
        "mask_id": 11,
        "mask_name": "MaskT (blue) (10 per pack)",
        "quantity": 1,
        "transaction_amount": 40.0,
        "transaction_date": "2023-01-01T10:00:00"
      },
      ...
    ]
    要求：
    1. 扣除 user.cash_balance
    2. 增加 pharmacy.cash_balance
    3. 新增 purchase_histories
    4. 如果任何一筆購買失敗，全部回滾(atomic)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 計算「所有購買」所需總金額
    total_amount_needed = sum(item.transaction_amount for item in items)
    if user.cash_balance < total_amount_needed:
        raise HTTPException(status_code=400, detail="User balance not enough for total purchase")

    # 開始交易
    try:
        # 逐筆檢查 & 寫入
        for item in items:
            # 找該筆的藥局
            pharmacy = db.query(Pharmacy).filter(Pharmacy.id == item.pharmacy_id).first()
            if not pharmacy:
                raise HTTPException(status_code=404, detail=f"Pharmacy id={item.pharmacy_id} not found")

            # 若有 mask_id，檢查是否存在
            if item.mask_id:
                m = db.query(Mask).filter(Mask.id == item.mask_id, Mask.pharmacy_id == pharmacy.id).first()
                if not m:
                    raise HTTPException(status_code=404, detail=f"Mask id={item.mask_id} not found in pharmacy {item.pharmacy_id}")

            # 核銷餘額
            user.cash_balance -= item.transaction_amount
            pharmacy.cash_balance += item.transaction_amount

            # 建立 purchase_histories
            new_record = PurchaseHistory(
                user_id=user.id,
                pharmacy_id=pharmacy.id,
                mask_id=item.mask_id,
                mask_name=item.mask_name,
                quantity=item.quantity,
                transaction_amount=item.transaction_amount,
                transaction_date=item.transaction_date
            )
            db.add(new_record)

        db.commit()
        db.refresh(user)
        # 也可 refresh 所有 pharmacy, new_record ...

    except HTTPException:
        # 如果是 HTTPException => 仍要 rollback
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {e}")

    return {"message": "Purchases processed successfully"}

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
