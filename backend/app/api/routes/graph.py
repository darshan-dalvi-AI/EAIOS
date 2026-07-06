"""Knowledge-graph API — nodes/edges for the Graph app + relational queries."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas import GraphOut
from app.services import kgraph

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=GraphOut)
def graph(q: str = "", limit: int = 60, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return kgraph.graph_data(db, q=q, limit=limit)


@router.get("/relate")
def relate(a: str, b: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    result = kgraph.relate(db, a, b)
    if result is None:
        raise HTTPException(404, "One or both entities were not found in the knowledge graph")
    return result
