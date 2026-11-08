"""Routes for the demo pages (ticket 10-03), on only when ``DEMO_PAGES`` is set.

The fictional shop pages (bubble and inline) and the low-budget page are static HTML, served by
the ``host`` service in ``docker compose`` and from the static bucket under ``/demo/`` in AWS. They
can't know the seeded Agents' public IDs, so they ask:

- ``GET /api/demo/agents``: which of the Demo Organisation's Agents to embed, and where the
  Embed Snippet's loader is served (the Studio's address).
- ``POST /api/demo/agents/{public_id}/exhaust-budget``: the low-budget page's button. It spends
  what is left of the low-budget Agent's Token Budget for today, as Visitor replies would, and
  raises its alert (and the Owners' email) the way the reply that spends a budget does. The next
  Visitor message gets the Agent's unavailable text. Only that one Agent can be exhausted.

Visitors are anonymous here, as in the widget API. Public IDs are public (they are in every
Embed Snippet), so neither route reveals anything a demo page doesn't already show. Not in the
OpenAPI document: no Studio code calls them.
"""


from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.api import ClockDep
from app.agents.models import Agent
from app.auth.api import Db
from app.embed import service
from app.embed.admission import utc_date
from app.embed.api import AdmissionDep
from app.seed import content
from app.tenancy.models import Member, Membership, Organisation, Role

NOT_SEEDED = "The demo isn't seeded yet. Run `make seed`."


def _demo_pages_on(request: Request) -> None:
    if not request.app.state.settings.demo_pages:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")


router = APIRouter(
    prefix="/api/demo", dependencies=[Depends(_demo_pages_on)], include_in_schema=False
)


class DemoAgentOut(BaseModel):
    public_id: str
    name: str


class BudgetAgentOut(DemoAgentOut):
    daily_token_budget: int


class DemoAgentsOut(BaseModel):
    # Where the Embed Snippet's loader is served: `<widget_url>/embed.js`.
    widget_url: str
    # The shop pages' Agent (bubble and inline layouts).
    shop: DemoAgentOut
    # The low-budget page's Agent.
    budget: BudgetAgentOut


class ExhaustedOut(BaseModel):
    tokens_used: int
    daily_token_budget: int


async def _demo_agents(db: AsyncSession) -> dict[str, Agent]:
    """The Demo Organisation's live, unarchived shop and low-budget Agents, by name."""
    found = await db.scalars(
        select(Agent)
        .join(Organisation, Organisation.id == Agent.organisation_id)
        .join(Membership, Membership.organisation_id == Organisation.id)
        .join(Member, Member.id == Membership.member_id)
        .where(
            Member.email == content.OWNER.email,
            Membership.role == Role.OWNER,
            Organisation.name == content.ORGANISATION_NAME,
            Agent.name.in_([content.SHOP_AGENT, content.BUDGET_AGENT]),
            Agent.archived_at.is_(None),
            Agent.live_version_id.is_not(None),
        )
    )
    return {agent.name: agent for agent in found}


@router.get("/agents")
async def demo_agents(request: Request, db: Db) -> DemoAgentsOut:
    agents = await _demo_agents(db)
    if set(agents) != {content.SHOP_AGENT, content.BUDGET_AGENT}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_SEEDED)
    shop, budget = agents[content.SHOP_AGENT], agents[content.BUDGET_AGENT]
    return DemoAgentsOut(
        widget_url=str(request.app.state.settings.studio_url).rstrip("/"),
        shop=DemoAgentOut(public_id=shop.public_id, name=shop.name),
        budget=BudgetAgentOut(
            public_id=budget.public_id,
            name=budget.name,
            daily_token_budget=budget.daily_token_budget,
        ),
    )


@router.post("/agents/{public_id}/exhaust-budget")
async def exhaust_budget(
    public_id: str, request: Request, db: Db, clock: ClockDep, admission: AdmissionDep
) -> ExhaustedOut:
    agent = (await _demo_agents(db)).get(content.BUDGET_AGENT)
    if agent is None or agent.public_id != public_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    now = clock.now()
    used = await admission.tokens_used(public_id, utc_date(now))
    if used < agent.daily_token_budget:
        used = await admission.record_usage(public_id, agent.daily_token_budget - used)
    await service.budget_exhausted(
        db,
        agent.id,
        mailer=request.app.state.mailer,
        studio_url=str(request.app.state.settings.studio_url),
        now=now,
    )
    return ExhaustedOut(tokens_used=used, daily_token_budget=agent.daily_token_budget)
