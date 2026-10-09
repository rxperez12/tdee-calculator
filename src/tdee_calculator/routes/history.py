from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select

from tdee_calculator import clock, entries
from tdee_calculator.export import entries_csv
from tdee_calculator.models import Entry
from tdee_calculator.web import SessionDependency, SettingsDependency, templates

router = APIRouter()


@router.get("/entries.csv")
def export_csv(session: SessionDependency) -> Response:
    filename = f"tdee-entries-{clock.today().isoformat()}.csv"
    return Response(
        content=entries_csv(entries.all_entries(session)),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


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
