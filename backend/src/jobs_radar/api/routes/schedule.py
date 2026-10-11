"""Daily schedule endpoints (document 07, section 5)."""

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_schedule_service, get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.schedule import ScheduleRead, ScheduleUpdate
from jobs_radar.services.schedule import ScheduleService, ScheduleView

router = APIRouter(tags=["schedule"])

Service = Annotated[ScheduleService, Depends(get_schedule_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def schedule_read(view: ScheduleView) -> ScheduleRead:
    """Map a schedule view to its API model."""
    setting = view.setting
    local = (
        view.next_run_at.astimezone(ZoneInfo(setting.timezone)).strftime("%Y-%m-%d %H:%M")
        if view.next_run_at
        else None
    )
    return ScheduleRead(
        run_time_local=setting.run_time_local.strftime("%H:%M"),
        timezone=setting.timezone,
        enabled=setting.enabled,
        company_recency_days=setting.company_recency_days,
        set_aside_below_fit=setting.set_aside_below_fit,
        version=setting.version,
        next_run_at=view.next_run_at,
        next_run_local=local,
    )


@router.get("/settings/schedule", response_model=ScheduleRead)
async def get_schedule(service: Service, session: Session) -> ScheduleRead:
    """Return the daily run time, time zone, enabled flag and the next scheduled run."""
    view = await service.get(LOCAL_OWNER_ID)
    await session.commit()  # the default row is created on first read
    return schedule_read(view)


@router.put("/settings/schedule", response_model=ScheduleRead)
async def update_schedule(body: ScheduleUpdate, service: Service, session: Session) -> ScheduleRead:
    """Change the schedule; the worker picks it up within one poll interval."""
    view = await service.update(
        LOCAL_OWNER_ID,
        run_time_local=body.run_time_local,
        timezone=body.timezone,
        enabled=body.enabled,
        company_recency_days=body.company_recency_days,
        set_aside_below_fit=body.set_aside_below_fit,
        expected_version=body.expected_version,
    )
    await session.commit()
    return schedule_read(view)
