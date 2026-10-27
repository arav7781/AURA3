"""Startups: the catalogue, profiles, registry checks and publishing."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from aura import publishing
from aura.access import is_owner, visible_startup
from aura.api.deps import Viewer, current_viewer, startup_owner
from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.core.errors import NotFound
from aura.evaluation import mca
from aura.models import Startup
from aura.models.startups import STAGES

router = APIRouter(prefix="/api", tags=["startups"])


def startup_card(startup: Startup) -> dict[str, Any]:
    return {
        "id": startup.id,
        "slug": startup.slug,
        "name": startup.name,
        "domain": startup.domain,
        "stage": startup.stage,
        "one_liner": startup.one_liner,
        "hq_city": startup.hq_city,
        "ask_inr": startup.ask_inr,
        "pre_money_inr": startup.pre_money_inr,
        "ai_score": startup.ai_score_x10 / 10 if startup.ai_score_x10 is not None else None,
        "recommendation": startup.recommendation,
        "mca_status": startup.mca_status,
        "compliance_flags": startup.compliance_flags,
        "status": startup.status,
        "published_at": clock.iso(startup.published_at) if startup.published_at else None,
    }


def startup_detail(startup: Startup) -> dict[str, Any]:
    return startup_card(startup) | {
        "legal_name": startup.legal_name,
        "sub_domain": startup.sub_domain,
        "description": startup.description,
        "profile": startup.profile,
        "hq_state": startup.hq_state,
        "founded_year": startup.founded_year,
        "cin": startup.cin,
        "mca": startup.mca,
        "latest_evaluation_id": startup.latest_evaluation_id,
    }


@router.get("/startups")
def catalogue(
    viewer: Viewer = Depends(current_viewer),
    q: str | None = Query(default=None, max_length=100),
    domain: str | None = None,
    stage: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=10),
    sort: Literal["score", "newest", "name", "ask"] = "score",
) -> dict[str, Any]:
    with read_session() as s:
        query = select(Startup).where(Startup.status == "published")
        if q:
            like = f"%{q.lower()}%"
            query = query.where(or_(func.lower(Startup.name).like(like), func.lower(Startup.one_liner).like(like),
                                    func.lower(Startup.domain).like(like)))
        if domain:
            query = query.where(Startup.domain == domain)
        if stage:
            query = query.where(Startup.stage == stage)
        if min_score is not None:
            query = query.where(Startup.ai_score_x10 >= round(min_score * 10))
        order = {
            "score": Startup.ai_score_x10.desc().nulls_last(),
            "newest": Startup.published_at.desc(),
            "name": Startup.name.asc(),
            "ask": Startup.ask_inr.desc(),
        }[sort]
        startups = s.scalars(query.order_by(order, Startup.name)).all()
        facets = {
            "domains": dict(s.execute(select(Startup.domain, func.count()).where(Startup.status == "published")
                                      .group_by(Startup.domain)).all()),
            "stages": dict(s.execute(select(Startup.stage, func.count()).where(Startup.status == "published")
                                     .group_by(Startup.stage)).all()),
        }
    return {"items": [startup_card(st) for st in startups], "facets": facets}


@router.get("/startups/{ref}")
def get_startup(ref: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, ref)
    detail = startup_detail(startup)
    detail["is_owner"] = is_owner(viewer, startup)
    return detail


class TeamMember(BaseModel):
    name: str = Field(max_length=80)
    role: str = Field(max_length=120)
    background: str = Field(default="", max_length=300)


class StartupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    legal_name: str | None = Field(default=None, max_length=200)
    domain: str | None = Field(default=None, max_length=60)
    stage: Literal[STAGES] | None = None  # type: ignore[valid-type]
    one_liner: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    hq_city: str | None = Field(default=None, max_length=80)
    hq_state: str | None = Field(default=None, max_length=80)
    founded_year: int | None = Field(default=None, ge=1990, le=2030)
    ask_inr: int | None = Field(default=None, gt=0)
    pre_money_inr: int | None = Field(default=None, gt=0)
    team: list[TeamMember] | None = Field(default=None, max_length=8)


@router.patch("/startups/{startup_id}")
def update_startup(startup_id: str, body: StartupUpdate, viewer: Viewer = Depends(startup_owner)) -> dict[str, Any]:
    if viewer.startup_id != startup_id and not viewer.is_admin:
        raise NotFound("Startup not found")
    with write_tx() as s:
        startup = s.get(Startup, startup_id)
        data = body.model_dump(exclude_none=True)
        team = data.pop("team", None)
        for field, value in data.items():
            setattr(startup, field, value)
        if team is not None:
            startup.profile = {**(startup.profile or {}), "team": team}
        startup.updated_at = clock.now()
        return startup_detail(startup)


class VerifyIn(BaseModel):
    cin: str = Field(min_length=5, max_length=32)


@router.post("/startups/{startup_id}/verify-mca")
def verify_mca(startup_id: str, body: VerifyIn, viewer: Viewer = Depends(startup_owner)) -> dict[str, Any]:
    if viewer.startup_id != startup_id and not viewer.is_admin:
        raise NotFound("Startup not found")
    with write_tx() as s:
        startup = s.get(Startup, startup_id)
        team = [m.get("name") for m in (startup.profile or {}).get("team", []) if m.get("name")]
        verification = mca.verify(body.cin, legal_name=startup.legal_name or startup.name, claimed_directors=team)
        flags = mca.consistency_flags(verification, legal_name=startup.legal_name or startup.name)
        kept = [f for f in startup.compliance_flags if not f.startswith(("MCA_", "COMPANY_STATUS_")) and f not in
                {"INVALID_CIN_FORMAT", "NAME_MISMATCH", "NO_DIRECTORS_FOUND", "SANDBOX_REGISTRY"}]
        startup.cin = verification.get("cin")
        startup.mca = verification
        startup.mca_status = verification.get("company_status")
        startup.compliance_flags = [*kept, *flags]
        startup.updated_at = clock.now()
        return {"verification": verification, "compliance_flags": startup.compliance_flags}


@router.post("/startups/{startup_id}/publish")
async def publish_startup(startup_id: str, viewer: Viewer = Depends(startup_owner)) -> dict[str, Any]:
    if viewer.startup_id != startup_id and not viewer.is_admin:
        raise NotFound("Startup not found")
    return startup_card(await publishing.publish_startup(startup_id))
