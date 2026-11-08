"""Builds the demo Organisation through the platform's own API, as a person in the Studio would.

``seed`` drives the FastAPI app in process, over HTTP: it signs up the demo Owner, invites and
signs up the Editor, adds the demo model's credential (and a real one, if given), sets the
Default Model and the Theme, creates the Project, its Tags, Documents and Agents, and publishes
the Agents the demo pages embed with the shop origin in their Allowed Origins (ticket 10-03).
So the seeded data is valid by construction. Files go to the object store through presigned URLs,
as a browser's do, and ingestion runs wherever the app sends it (the worker, or eagerly in tests).

It is idempotent: it finds the demo Organisation through the demo Owner's account and only
adds what is missing or changes what differs, so running it again changes nothing.

``reset`` erases the demo Organisation and the demo accounts (``app.tenancy.erasure``), then
seeds again. It touches no other Organisation, and refuses to run if a demo account has joined
one.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from app.credentials.registry import PROVIDERS, Provider
from app.seed import content
from app.storage.memory import InMemoryObjectStore
from app.tenancy.erasure import erase_member, erase_organisation
from app.tenancy.models import Member, Membership, Organisation, Role

# HTTPS, so the client's cookie jar sends the Secure session cookie back.
BASE_URL = "https://seed.internal"


class SeedError(Exception):
    """The seed can't go on; the message says why and what to do."""


@dataclass(frozen=True)
class RealCredential:
    """A real Provider Credential to demo real answers with, read from the environment."""

    provider: Provider
    api_key: str
    model: str


def real_credential_from_env(environ: Mapping[str, str]) -> RealCredential | None:
    """``SEED_CREDENTIAL_PROVIDER`` (anthropic or openai) and ``SEED_CREDENTIAL_API_KEY``,
    with an optional ``SEED_CREDENTIAL_MODEL``; none of them means the demo model answers."""
    provider = environ.get("SEED_CREDENTIAL_PROVIDER", "").strip().lower()
    api_key = environ.get("SEED_CREDENTIAL_API_KEY", "").strip()
    if not provider and not api_key:
        return None
    choices = {p.value: p for p in content.REAL_DEFAULT_MODELS}
    if provider not in choices or not api_key:
        raise SeedError(
            "Set both SEED_CREDENTIAL_PROVIDER (anthropic or openai) and "
            "SEED_CREDENTIAL_API_KEY to seed a real credential, or neither."
        )
    chosen = choices[provider]
    model = environ.get("SEED_CREDENTIAL_MODEL", "").strip() or content.REAL_DEFAULT_MODELS[chosen]
    return RealCredential(chosen, api_key, model)


@dataclass(frozen=True)
class SeedReport:
    organisation_id: str
    studio_url: str
    default_model: str
    documents: int
    demo_pages_url: str

    def lines(self) -> list[str]:
        return [
            f"Seeded the demo Organisation {content.ORGANISATION_NAME!r}.",
            f"Studio: {self.studio_url}",
            f"  Owner:  {content.OWNER.email}  password: {content.OWNER.password}",
            f"  Editor: {content.EDITOR.email}  password: {content.EDITOR.password}",
            f"Project {content.PROJECT_NAME!r}: {self.documents} Documents "
            "(ingestion may take a minute).",
            f"Default Model: {self.default_model}",
            f"Demo pages: {self.demo_pages_url}",
        ]


class _Api:
    """A signed-in client, raising ``SeedError`` on any answer but the expected one."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.organisation = ""

    def path(self, *parts: str) -> str:
        return "/".join(["/api/organisations", self.organisation, *parts])

    async def call(self, method: str, path: str, *, expect: int = 200, body: Any = None) -> Any:
        response = await self.client.request(method, path, json=body)
        if response.status_code != expect:
            raise SeedError(f"{method} {path} answered {response.status_code}: {response.text}")
        return response.json()


async def _put_file(app: FastAPI, url: str, data: bytes, content_type: str) -> None:
    """What the browser's PUT to a presigned URL does."""
    store = app.state.ingestion.object_store
    if isinstance(store, InMemoryObjectStore):  # tests: the URL names the key
        await store.put(unquote(urlsplit(url).path.lstrip("/")), data, content_type=content_type)
        return
    async with httpx.AsyncClient() as http:
        response = await http.put(url, content=data, headers={"Content-Type": content_type})
    response.raise_for_status()


async def _owner(api: _Api) -> None:
    owner = content.OWNER
    response = await api.client.post(
        "/api/auth/sign-up",
        json={
            "name": owner.name,
            "email": owner.email,
            "password": owner.password,
            "organisation_name": content.ORGANISATION_NAME,
        },
    )
    if response.status_code == 409:  # seeded before: sign in instead
        response = await api.client.post(
            "/api/auth/sign-in", json={"email": owner.email, "password": owner.password}
        )
    if response.status_code not in (200, 201):
        raise SeedError(
            f"Can't sign in as the demo Owner {owner.email} ({response.status_code}). "
            "Run `make seed-reset` to recreate the demo Organisation."
        )
    organisations = response.json()["organisations"]
    found = [
        o["id"]
        for o in organisations
        if o["name"] == content.ORGANISATION_NAME and o["role"] == Role.OWNER
    ]
    if not found:
        raise SeedError(
            f"{owner.email} owns no Organisation named {content.ORGANISATION_NAME!r}. "
            "Run `make seed-reset` to recreate it."
        )
    api.organisation = found[0]


async def _editor(app: FastAPI, api: _Api) -> None:
    editor = content.EDITOR
    members = await api.call("GET", api.path("members"))
    if any(m["email"] == editor.email for m in members):
        return
    issued = await api.call(
        "POST",
        api.path("invites"),
        expect=201,
        body={"email": editor.email, "role": Role.EDITOR, "send_email": False},
    )
    (token,) = parse_qs(urlsplit(issued["link"]).query)["token"]
    async with _client(app) as client:
        await _Api(client).call(
            "POST",
            "/api/invites/sign-up",
            expect=201,
            body={"token": token, "name": editor.name, "password": editor.password},
        )


async def _credential(api: _Api, name: str, provider: Provider, api_key: str) -> str:
    credentials = await api.call("GET", api.path("credentials"))
    for credential in credentials:
        if credential["name"] == name:
            existing: str = credential["id"]
            return existing
    created = await api.call(
        "POST",
        api.path("credentials"),
        expect=201,
        body={"name": name, "provider": provider, "api_key": api_key},
    )
    new: str = created["id"]
    return new


async def _default_model(api: _Api, real: RealCredential | None) -> str:
    demo = await _credential(api, content.DEMO_CREDENTIAL, Provider.DEMO, content.DEMO_KEY)
    chosen = (demo, content.DEMO_MODEL)
    if real is not None:
        name = f"Northwind {PROVIDERS[real.provider].name}"
        chosen = (await _credential(api, name, real.provider, real.api_key), real.model)
    current = await api.call("GET", api.path("default-model"))
    if current is None or (current["credential_id"], current["model"]) != chosen:
        current = await api.call(
            "PUT",
            api.path("default-model"),
            body={"credential_id": chosen[0], "model": chosen[1]},
        )
    return f"{current['model_name']} ({current['credential_name']})"


async def _theme(api: _Api) -> None:
    wanted = content.THEME.model_dump(mode="json")
    current = await api.call("GET", api.path("theme"))
    if {key: current[key] for key in wanted} != wanted:
        await api.call("PUT", api.path("theme"), body=wanted)


async def _project(api: _Api) -> str:
    projects = await api.call("GET", api.path("projects"))
    found = [p["id"] for p in projects if p["name"] == content.PROJECT_NAME]
    if found:
        existing: str = found[0]
        return existing
    created = await api.call(
        "POST",
        api.path("projects"),
        expect=201,
        body={"name": content.PROJECT_NAME, "description": content.PROJECT_DESCRIPTION},
    )
    new: str = created["id"]
    return new


async def _tags(api: _Api, project: str) -> dict[str, str]:
    tags = {
        t["name"]: t["id"] for t in await api.call("GET", api.path("projects", project, "tags"))
    }
    for name in (content.HR, content.PRODUCTS):
        if name not in tags:
            created = await api.call(
                "POST", api.path("projects", project, "tags"), expect=201, body={"name": name}
            )
            tags[name] = created["id"]
    return tags


async def _documents(
    app: FastAPI, api: _Api, project: str, assets: Path, tags: dict[str, str]
) -> int:
    documents = api.path("projects", project, "documents")
    existing = {d["name"]: d for d in await api.call("GET", documents)}
    for wanted in content.DOCUMENTS:
        document = existing.get(wanted.filename)
        if document is None:
            data = (assets / "documents" / wanted.filename).read_bytes()
            ticket = await api.call(
                "POST",
                api.path("projects", project, "uploads"),
                expect=201,
                body={"filename": wanted.filename, "size_bytes": len(data)},
            )
            await _put_file(app, ticket["url"], data, ticket["content_type"])
            document = await api.call(
                "POST", documents, expect=201, body={"upload_id": ticket["upload_id"]}
            )
        tag_ids = sorted(tags[name] for name in wanted.tags)
        if sorted(t["id"] for t in document["tags"]) != tag_ids:
            await api.call("PUT", f"{documents}/{document['id']}/tags", body={"tag_ids": tag_ids})
    return len(content.DOCUMENTS)


def shop_origin(app: FastAPI) -> str:
    """The origin the demo pages are served from: ``DEMO_SHOP_ORIGIN``, else the Studio's."""
    settings = app.state.settings
    url = urlsplit(str(settings.demo_shop_origin or settings.studio_url))
    return f"{url.scheme}://{url.netloc}"


async def _embedding(
    api: _Api, agent_path: str, agent: Any, embedding: content.Embedding, origin: str
) -> None:
    """Publishes the Agent if it isn't Live, and sets what the demo pages need of its
    Operational Settings."""
    if agent["live_version"] is None:
        await api.call(
            "POST", f"{agent_path}/versions", expect=201, body={"note": content.PUBLISH_NOTE}
        )
    settings_path = f"{agent_path}/operational-settings"
    current = await api.call("GET", settings_path)
    wanted: dict[str, Any] = {
        "allowed_origins": [origin],
        "daily_token_budget": embedding.daily_token_budget,
        "unavailable_text": embedding.unavailable_text,
    }
    if {key: current[key] for key in wanted} != wanted:
        await api.call("PATCH", settings_path, body=wanted)


async def _agents(api: _Api, project: str, tags: dict[str, str], origin: str) -> None:
    agents = api.path("projects", project, "agents")
    existing = {a["name"]: a for a in await api.call("GET", agents)}
    for wanted in content.AGENTS:
        agent = existing.get(wanted.name)
        if agent is None:
            agent = await api.call("POST", agents, expect=201, body={"name": wanted.name})
        draft = agent["draft"]
        changed = {
            **draft,
            "behaviour": {**draft["behaviour"], "system_prompt": wanted.system_prompt},
            "retrieval": {
                **draft["retrieval"],
                "tag_ids": sorted(tags[name] for name in wanted.tags),
            },
            "experience": {**draft["experience"], "greeting": wanted.greeting},
        }
        if changed != draft:
            await api.call("PUT", f"{agents}/{agent['id']}/draft", body=changed)
        if wanted.embedding is not None:
            await _embedding(api, f"{agents}/{agent['id']}", agent, wanted.embedding, origin)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)


async def seed(app: FastAPI, assets: Path, real: RealCredential | None = None) -> SeedReport:
    """Builds, or completes, the demo Organisation. ``assets`` is the ``seed`` folder."""
    async with _client(app) as client:
        api = _Api(client)
        await _owner(api)
        await _editor(app, api)
        default_model = await _default_model(api, real)
        await _theme(api)
        project = await _project(api)
        tags = await _tags(api, project)
        documents = await _documents(app, api, project, assets, tags)
        origin = shop_origin(app)
        await _agents(api, project, tags, origin)
    return SeedReport(
        organisation_id=api.organisation,
        studio_url=str(app.state.settings.studio_url),
        default_model=default_model,
        documents=documents,
        demo_pages_url=f"{origin}/demo/",
    )


async def erase_demo(app: FastAPI) -> None:
    """Erases the demo Organisation and the demo accounts; nothing else."""
    async with app.state.sessionmaker() as session:
        emails = [content.OWNER.email, content.EDITOR.email]
        ids = list(await session.scalars(select(Member.id).where(Member.email.in_(emails))))
        demo: list[uuid.UUID] = list(
            await session.scalars(
                select(Organisation.id)
                .join(Membership, Membership.organisation_id == Organisation.id)
                .join(Member, Member.id == Membership.member_id)
                .where(
                    Member.email == content.OWNER.email,
                    Membership.role == Role.OWNER,
                    Organisation.name == content.ORGANISATION_NAME,
                )
            )
        )
        elsewhere = await session.scalar(
            select(Member.email)
            .join(Membership, Membership.member_id == Member.id)
            .where(Member.id.in_(ids), Membership.organisation_id.not_in(demo))
            .limit(1)
        )
        if elsewhere is not None:
            raise SeedError(
                f"The demo account {elsewhere} belongs to another Organisation too. "
                "Remove it there first; nothing was erased."
            )
        for organisation_id in demo:
            await erase_organisation(session, app.state.ingestion.object_store, organisation_id)
        for member_id in ids:
            await erase_member(session, member_id)


async def reset(app: FastAPI, assets: Path, real: RealCredential | None = None) -> SeedReport:
    """Erases the demo Organisation and seeds it again."""
    await erase_demo(app)
    return await seed(app, assets, real)
