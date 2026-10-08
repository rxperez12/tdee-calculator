from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from tdee_calculator import entries
from tdee_calculator.models import Entry
from tdee_calculator.web import SessionDependency, SettingsDependency, templates

router = APIRouter()


@router.get("/history")
def history(
    request: Request, session: SessionDependency, settings: SettingsDependency
) -> HTMLResponse:
    entry_count = session.scalar(select(func.count()).select_from(Entry)) or 0
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "entry_count": entry_count,
            "recent_entries": entries.recent_entries(session),
            "settings": settings,
        },
    )
