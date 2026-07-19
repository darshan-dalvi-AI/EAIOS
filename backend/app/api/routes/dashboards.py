"""NL-to-BI — describe a chart in English, get a rendered chart; pin to a dashboard."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.sql_agent import SQLAgent
from app.api.deps import get_current_user, get_db
from app.models import SavedChart, User
from app.services import audit, charts

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


class ChartIn(BaseModel):
    question: str = Field(min_length=2, max_length=400)


@router.post("/chart")
def make_chart(body: ChartIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """NL → safe SQL (SQL Agent) → executed → inferred chart spec."""
    out = SQLAgent(db, user).answer(body.question)
    spec = charts.infer_chart(body.question, out.columns, out.rows)
    audit.log(db, "dashboard.chart", user.id, f"{body.question[:80]} → {spec['type']}")
    return {"question": body.question, "sql": out.sql, "explanation": out.explanation,
            "warning": out.warning, **spec}


class PinIn(BaseModel):
    question: str
    sql: str = ""
    spec: dict


@router.get("")
def list_charts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(SavedChart).where(SavedChart.owner_id == user.id).order_by(SavedChart.created_at.desc())).all()
    return [{"id": c.id, "question": c.question, "sql": c.sql, "spec": json.loads(c.spec or "{}"),
             "created_at": c.created_at.isoformat()} for c in rows]


@router.post("", status_code=201)
def pin_chart(body: PinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chart = SavedChart(owner_id=user.id, question=body.question[:400], sql=body.sql,
                       spec=json.dumps(body.spec))
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return {"id": chart.id}


@router.delete("/{chart_id}", status_code=204)
def unpin_chart(chart_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chart = db.get(SavedChart, chart_id)
    if chart is None or chart.owner_id != user.id:
        raise HTTPException(404, "Chart not found")
    db.delete(chart)
    db.commit()
