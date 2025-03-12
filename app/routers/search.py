# app/routers/search.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any, Dict, List
from app.database import get_db
from app.models import Pharmacy, Mask

router = APIRouter(prefix="/search", tags=["Search"])

@router.get("/")
def search_pharmacies_and_masks(q: str, db: Session = Depends(get_db)):
    """
    Search for pharmacies or masks by name, ranked by 'relevance'.
    這裡以非常簡單的做法: 先查 pharmacy，再查 mask，
    然後按照 name 長度 or match 位置去做簡易排序 (僅示範)。
    """
    # 1) 查 pharmacies
    phar_results = db.query(Pharmacy).filter(Pharmacy.name.ilike(f"%{q}%")).all()

    # 2) 查 masks
    mask_results = db.query(Mask).filter(Mask.name.ilike(f"%{q}%")).all()

    # 建立一個合併清單
    # 注意: "rank" 這裡只是示範，以 name.index(...) 來衡量簡易關聯度
    combined: List[Dict[str, Any]] = []

    for p in phar_results:
        rank_score = 0
        try:
            # 字串中出現 q 的位置
            idx = p.name.lower().index(q.lower())
            rank_score = 100 - idx  # idx 越小 => rank_score 越高
        except ValueError:
            pass
        combined.append({
            "type": "pharmacy",
            "pharmacy_id": p.id,
            "name": p.name,
            "cash_balance": p.cash_balance,
            "rank": rank_score
        })

    for m in mask_results:
        rank_score = 0
        try:
            idx = m.name.lower().index(q.lower())
            rank_score = 100 - idx
        except ValueError:
            pass
        combined.append({
            "type": "mask",
            "mask_id": m.id,
            "pharmacy_id": m.pharmacy_id,
            "name": m.name,
            "price": m.price,
            "rank": rank_score
        })

    # 依 rank_score desc 排序
    combined.sort(key=lambda x: x["rank"], reverse=True)

    return combined
