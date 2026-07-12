"""Report exports — download any agent answer as a PDF or DOCX artifact."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.services import audit, reports

router = APIRouter(prefix="/reports", tags=["reports"])

_MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown; charset=utf-8",
}


class ExportIn(BaseModel):
    title: str = Field(default="EAIOS Report", max_length=140)
    content: str = Field(min_length=1, max_length=200_000)  # markdown (an agent answer)
    format: str = Field(default="pdf", pattern="^(pdf|docx|md)$")


@router.post("/export")
def export_report(body: ExportIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Render markdown (usually a Report-agent answer) into a downloadable file."""
    try:
        if body.format == "pdf":
            data = reports.build_pdf(body.title, body.content)
        elif body.format == "docx":
            data = reports.build_docx(body.title, body.content)
        else:
            data = body.content.encode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Export failed: {exc}") from exc

    filename = reports.safe_filename(body.title, body.format)
    audit.log(db, "report.export", user.id, f"{filename} ({len(data)} bytes)")
    return Response(
        content=data,
        media_type=_MEDIA[body.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
