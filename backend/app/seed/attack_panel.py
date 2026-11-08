"""The attack panel's debug endpoint (ticket 10-04), on only in demo mode (``DEMO_PAGES``).

The attack panel is a static demo page (``/demo/attacks.html``) with one button per attack
category and a benign control. It fires fixed payloads (``content.ATTACKS``) at the Demo
Organisation's Guardrail demo Agent and shows the reply and which Guardrail layer acted:

- ``GET /api/demo/attacks``: the Agent and the attacks, for the buttons.
- ``POST /api/demo/attacks/{attack_id}``: sends that attack's payload to the Agent's Live Version
  exactly as the widget does (a new Visitor Conversation, admission control, the Guardrail
  pipeline, the answer saved with its Trace) and streams the same Server-Sent Events the widget
  gets (``token``, ``citation``, ``replace``, ``refusal``, ``error``, ``unavailable``). Before
  ``done`` it adds what a Visitor never sees, the ``trace`` event: each Guardrail layer's
  outcome (the input Guardrail: ``blocked``, ``flagged``, ``logged``, ``allowed`` or ``passed``;
  the Canary token: ``replaced``, ``flagged``, ``quiet``, or ``not_reached`` when the input
  Guardrail blocked the message), which layers acted, the model asked and the saved answer.

Like a Playground's Trace, but without a Studio login, which is why it exists only in demo mode.
Only the fixed payloads can be sent, so it is no free chat endpoint; the Agent's rate limits
apply, and as in the Playground its replies don't count against the Token Budget. Not in the
OpenAPI document: no Studio code calls it.
"""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.api import ClockDep
from app.auth.api import Db
from app.embed import service
from app.embed.admission import Refusal
from app.embed.api import (
    BUDGET_EXHAUSTED,
    RATE_LIMITED,
    AdmissionDep,
    Signer,
    VisitorIp,
)
from app.guardrails.pipeline import RefusalEvent
from app.playground.service import Answered, answer
from app.runtime.errors import ErrorEvent
from app.runtime.runtime import CitationEvent, ReplaceEvent, TokenEvent
from app.seed import content
from app.seed.demo_pages import NOT_SEEDED, demo_pages_on, live_demo_agents

router = APIRouter(
    prefix="/api/demo/attacks", dependencies=[Depends(demo_pages_on)], include_in_schema=False
)

# The layers in the order they act, with the names the panel shows.
LAYER_NAMES = {"input": "Input Guardrail", "canary": "Canary token"}
# What a layer that did nothing reports.
INPUT_PASSED, CANARY_QUIET, NOT_REACHED = "passed", "quiet", "not_reached"


class AttackAgentOut(BaseModel):
    public_id: str
    name: str


class AttackOut(BaseModel):
    id: str
    category: str
    label: str
    payload: str
    # What the Guardrails are expected to do about it (with the local classifier).
    expected: str


class AttackPanelOut(BaseModel):
    agent: AttackAgentOut
    attacks: list[AttackOut]


async def _target(db: Db) -> AttackAgentOut:
    found = (await live_demo_agents(db, content.ATTACK_AGENT)).get(content.ATTACK_AGENT)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_SEEDED)
    return AttackAgentOut(public_id=found.public_id, name=found.name)


@router.get("")
async def attack_panel(db: Db) -> AttackPanelOut:
    return AttackPanelOut(
        agent=await _target(db),
        attacks=[
            AttackOut(
                id=a.id, category=a.category, label=a.label, payload=a.payload, expected=a.expected
            )
            for a in content.ATTACKS
        ],
    )


def layers(outcomes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each Guardrail layer's outcome for one answer, in the order the layers act: the saved
    outcome of a layer that acted, else what it reports when it did nothing."""
    found = {o["layer"]: o for o in outcomes}
    blocked = found.get("input", {}).get("action") == "blocked"
    idle = {"input": INPUT_PASSED, "canary": NOT_REACHED if blocked else CANARY_QUIET}
    result = []
    for layer, name in LAYER_NAMES.items():
        outcome = found.get(layer)
        result.append(
            {
                "layer": layer,
                "name": name,
                "action": idle[layer] if outcome is None else outcome["action"],
                "verdict": None if outcome is None else outcome["verdict"],
                "reason": None if outcome is None else outcome["reason"],
                "score": None if outcome is None else outcome["score"],
            }
        )
    return result


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{attack_id}")
async def fire_attack(
    attack_id: str,
    request: Request,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    admission: AdmissionDep,
    ip: VisitorIp,
) -> StreamingResponse:
    attack = next((a for a in content.ATTACKS if a.id == attack_id), None)
    if attack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    public_id = (await _target(db)).public_id
    unavailable = await service.unavailable_text(db, public_id)
    # A new Visitor Conversation, as the widget starts one.
    shell = await service.shell(db, signer, public_id, now=clock.now())
    token = await service.start_conversation(
        db, signer, public_id, shell.bootstrap_token, now=clock.now()
    )
    try:
        admitted = await service.prepare_turn(
            db,
            signer,
            public_id,
            token,
            attack.payload,
            admission=admission,
            ip=ip,
            now=clock.now(),
        )
    except service.NotAdmittedError as refused:
        reason = BUDGET_EXHAUSTED if refused.reason is Refusal.TOKEN_BUDGET else RATE_LIMITED
        return _stream(_one(_sse("unavailable", {"reason": reason, "message": unavailable})))
    prepared = admitted.turn
    state = request.app.state

    async def events() -> AsyncIterator[str]:
        async for event in answer(
            prepared,
            sessionmaker=state.sessionmaker,
            gateway=state.model_gateway,
            guardrails=state.guardrails,
            embedders=state.ingestion.embedders,
            clock=state.clock,
        ):
            if isinstance(event, TokenEvent):
                yield _sse("token", {"text": event.text})
            elif isinstance(event, ReplaceEvent):
                yield _sse("replace", {"text": event.text})
            elif isinstance(event, RefusalEvent):
                yield _sse("refusal", {"text": event.text})
            elif isinstance(event, ErrorEvent):
                yield _sse("error", {"code": event.kind, "message": unavailable})
            elif isinstance(event, CitationEvent):
                yield _sse(
                    "citation",
                    {
                        "label": event.label,
                        "document_name": event.chunk.document_name,
                        "passage": event.chunk.text,
                    },
                )
            else:
                yield _sse("trace", _trace(event, prepared.chat.model))
                yield _sse("done", {"message_id": str(event.message_id)})

    return _stream(events())


def _trace(answered: Answered, model: str) -> dict[str, Any]:
    done = answered.event
    found = layers([o.as_dict() for o in done.guardrail_outcomes])
    acted = [
        layer["layer"]
        for layer in found
        if layer["action"] not in (INPUT_PASSED, CANARY_QUIET, NOT_REACHED)
    ]
    return {
        "message_id": str(answered.message_id),
        "layers": found,
        "acted": ", ".join(acted) or None,
        # A refusal (or a fallback reply) asked no model.
        "model": None if done.refused or done.fallback else model,
        "answer": done.answer,
    }


async def _one(event: str) -> AsyncIterator[str]:
    yield event
