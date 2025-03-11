from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.database import get_db
from app.models import User, Pharmacy, PurchaseHistory
from app.schemas import User as UserSchema
from app.schemas import PurchaseHistory as PurchaseHistorySchema
from app.schemas import PurchaseHistoryCreate

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/", response_model=List[UserSchema])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@router.get("/{user_id}/purchases", response_model=List[PurchaseHistorySchema])
def get_user_purchases(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.purchase_histories  # Relationship

@router.post("/{user_id}/purchase")
def purchase_mask(user_id: int, purchase_data: PurchaseHistoryCreate, db: Session = Depends(get_db)):
    """
    讓使用者購買口罩，需同時更新:
      - user.cash_balance -= purchase_data.transaction_amount
      - pharmacy.cash_balance += purchase_data.transaction_amount
      - 新增一筆 purchase_histories
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pharmacy = db.query(Pharmacy).filter(Pharmacy.id == purchase_data.pharmacy_id).first()
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")

    # 檢查使用者餘額
    amount = purchase_data.transaction_amount
    if user.cash_balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient user balance")

    # 更新餘額 (同一個 DB session => 交易原子性)
    user.cash_balance -= amount
    pharmacy.cash_balance += amount

    # 建立 purchase_histories
    new_purchase = PurchaseHistory(
        user_id=user.id,
        pharmacy_id=pharmacy.id,
        mask_name=purchase_data.mask_name,
        transaction_amount=amount,
        transaction_date=purchase_data.transaction_date
    )
    db.add(new_purchase)

    db.commit()
    db.refresh(user)
    db.refresh(pharmacy)
    db.refresh(new_purchase)

    return {"message": "Purchase successful", "purchase_id": new_purchase.id}