"""Investor reviews and the community ranking board.

Founders see the reviews of their own startup with reviewers anonymised; investors see names and plans.
"""

import string
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from aura.access import is_owner, visible_startup
from aura.api.deps import Viewer, current_viewer, investor
from aura.api.routes.startups import startup_card
from aura.core import clock
from aura.core.db import read_session, write_tx
from aura.core.errors import AppError, NotFound
from aura.models import InvestorProfile, Ranking, Review, Startup, User
from aura.rankings import Ballot, community_scores, ranks

router = APIRouter(prefix="/api", tags=["community"])
DIMENSIONS = ("team", "market", "product", "traction")


class ReviewIn(BaseModel):
    team: int = Field(ge=1, le=5)
    market: int = Field(ge=1, le=5)
    product: int = Field(ge=1, le=5)
    traction: int = Field(ge=1, le=5)
    note: str = Field(default="", max_length=2000)


def _review_out(review: Review, reviewer: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": review.id, **{d: getattr(review, d) for d in DIMENSIONS}, "note": review.note,
        "average": round(sum(getattr(review, d) for d in DIMENSIONS) / 4, 2),
        "reviewer": reviewer, "created_at": clock.iso(review.created_at),
        "updated_at": clock.iso(review.updated_at) if review.updated_at else None,
    }


@router.get("/startups/{startup_id}/reviews")
def list_reviews(startup_id: str, viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    anonymise = is_owner(viewer, startup) and not viewer.is_admin
    with read_session() as s:
        rows = s.execute(
            select(Review, User.name, InvestorProfile.plan)
            .join(User, User.id == Review.investor_id)
            .outerjoin(InvestorProfile, InvestorProfile.user_id == Review.investor_id)
            .where(Review.startup_id == startup.id)
            .order_by(Review.created_at)
        ).all()
    items, mine = [], None
    for index, (review, name, plan) in enumerate(rows):
        label = f"Investor {string.ascii_uppercase[index % 26]}{index // 26 or ''}"
        out = _review_out(review, {"name": label} if anonymise else {"name": name, "plan": plan})
        items.append(out)
        if review.investor_id == viewer.user_id:
            mine = out
    summary = {"count": len(items)}
    if items:
        summary |= {d: round(sum(i[d] for i in items) / len(items), 2) for d in DIMENSIONS}
        summary["average"] = round(sum(i["average"] for i in items) / len(items), 2)
    return {"items": items, "summary": summary, "mine": mine}


@router.put("/startups/{startup_id}/review")
def put_review(startup_id: str, body: ReviewIn, viewer: Viewer = Depends(investor)) -> dict[str, Any]:
    startup = visible_startup(viewer, startup_id)
    with write_tx() as s:
        review = s.scalar(select(Review).where(Review.startup_id == startup.id, Review.investor_id == viewer.user_id))
        if review is None:
            review = Review(startup_id=startup.id, investor_id=viewer.user_id, **body.model_dump())
            s.add(review)
        else:
            for key, value in body.model_dump().items():
                setattr(review, key, value)
            review.updated_at = clock.now()
        s.flush()
        name = s.get(User, viewer.user_id).name
        return _review_out(review, {"name": name})


@router.delete("/startups/{startup_id}/review", status_code=204)
def delete_review(startup_id: str, viewer: Viewer = Depends(investor)) -> None:
    startup = visible_startup(viewer, startup_id)
    with write_tx() as s:
        s.execute(delete(Review).where(Review.startup_id == startup.id, Review.investor_id == viewer.user_id))


def _ballots(s: Any) -> list[Ballot]:
    rows = s.execute(
        select(Ranking.investor_id, Ranking.startup_id, Ranking.position, InvestorProfile.plan,
               InvestorProfile.reputation_milli)
        .join(InvestorProfile, InvestorProfile.user_id == Ranking.investor_id)
        .order_by(Ranking.investor_id, Ranking.position)
    ).all()
    lists: dict[str, tuple[str, float, list[str]]] = {}
    for investor_id, startup_id, _, plan, reputation in rows:
        lists.setdefault(investor_id, (plan, reputation / 1000, []))[2].append(startup_id)
    return [Ballot(i, plan, rep, ids) for i, (plan, rep, ids) in lists.items()]


@router.get("/rankings")
def rankings(viewer: Viewer = Depends(current_viewer)) -> dict[str, Any]:
    with read_session() as s:
        startups = {st.id: st for st in s.scalars(select(Startup).where(Startup.status == "published"))}
        ballots = [b for b in _ballots(s) if b.startup_ids]
        mine = s.scalars(select(Ranking.startup_id).where(Ranking.investor_id == viewer.user_id)
                         .order_by(Ranking.position)).all()
    scores = {k: v for k, v in community_scores(ballots).items() if k in startups}
    community_rank = ranks({k: v["score"] for k, v in scores.items()})
    ai = {k: st.ai_score_x10 / 10 for k, st in startups.items() if st.ai_score_x10 is not None}
    ai_rank = ranks(ai)
    board = []
    for startup_id, score in scores.items():
        card = startup_card(startups[startup_id])
        board.append(card | {
            "community_score": score["score"], "community_rank": community_rank[startup_id],
            "rankers": score["rankers"], "ai_rank": ai_rank.get(startup_id),
            # positive: the community rates it higher than the AI does
            "rank_gap": ai_rank[startup_id] - community_rank[startup_id] if startup_id in ai_rank else None,
        })
    board.sort(key=lambda row: (row["community_rank"], row["name"]))
    return {
        "board": board,
        "mine": [startup_card(startups[i]) for i in mine if i in startups],
        "ballots": len(ballots),
        "method": "Weighted truncated Borda count over each investor's top 10 (10 points for #1 … 1 for #10). "
                  "Weight = plan (Scout 0.5, Angel/Syndicate 1.0) × reputation (0.5–2.0).",
    }


class RankingIn(BaseModel):
    startup_ids: list[str] = Field(max_length=10)


@router.put("/me/ranking")
def put_ranking(body: RankingIn, viewer: Viewer = Depends(investor)) -> dict[str, Any]:
    if len(set(body.startup_ids)) != len(body.startup_ids):
        raise AppError("Each startup can appear once", code="DUPLICATE_STARTUP")
    with write_tx() as s:
        published = set(s.scalars(select(Startup.id).where(Startup.id.in_(body.startup_ids),
                                                           Startup.status == "published")))
        missing = [i for i in body.startup_ids if i not in published]
        if missing:
            raise NotFound("Startup not found", startup_ids=missing)
        s.execute(delete(Ranking).where(Ranking.investor_id == viewer.user_id))
        s.flush()
        for position, startup_id in enumerate(body.startup_ids, start=1):
            s.add(Ranking(investor_id=viewer.user_id, startup_id=startup_id, position=position))
    return {"startup_ids": body.startup_ids}
