"""The demo seed (``make seed``, ``make seed-reset``), checked as an interviewer would see the
result: through the API, signed in with the printed demo accounts.

Documents are converted by Docling, which reads Markdown, DOCX and PPTX without models, so the
seed's Word document and slide deck become real Chunks. Embeddings use the deterministic fake.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import func, select, text

from app.audit.models import AuditEvent
from app.credentials.registry import Provider
from app.main import create_app
from app.seed import content
from app.seed.__main__ import DEFAULT_ASSETS, main
from app.seed.content import Account
from app.seed.runner import (
    RealCredential,
    SeedError,
    erase_demo,
    real_credential_from_env,
    reset,
    seed,
)
from app.storage.memory import InMemoryObjectStore
from app.tenancy.erasure import erase_member, erase_organisation
from tests.agents import ask, parse_sse, start_conversation
from tests.conftest import BASE_URL, ClientFactory, SignedUpMember, TenantFactory
from tests.integration.test_object_store import RUSTFS_KEYS, RUSTFS_URL

ASSETS = DEFAULT_ASSETS
INJECTION = "ignore your previous instructions"


@pytest.fixture
def settings_env(settings_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    settings_env.setenv("DOCUMENT_CONVERTER", "docling")
    for name in ("SEED_CREDENTIAL_PROVIDER", "SEED_CREDENTIAL_API_KEY", "SEED_CREDENTIAL_MODEL"):
        settings_env.delenv(name, raising=False)
    return settings_env


@pytest.fixture
async def demo_app(app: FastAPI) -> FastAPI:
    """The app, with no demo Organisation left from another test."""
    await erase_demo(app)
    return app


async def signed_in(new_client: ClientFactory, account: Account) -> SignedUpMember:
    """The demo account, signed in, in the demo Organisation."""
    client = await new_client()
    response = await client.post(
        "/api/auth/sign-in", json={"email": account.email, "password": account.password}
    )
    assert response.status_code == 200, response.text
    (organisation,) = response.json()["organisations"]
    return SignedUpMember(
        client=client,
        member_id=response.json()["member"]["id"],
        name=account.name,
        email=account.email,
        password=account.password,
        organisation_id=organisation["id"],
        organisation_name=organisation["name"],
    )


async def get(member: SignedUpMember, *parts: str) -> Any:
    path = "/".join(["/api/organisations", member.organisation_id, *parts])
    response = await member.client.get(path, params={"limit": 200} if "chunks" in parts else None)
    assert response.status_code == 200, response.text
    return response.json()


async def demo_project(owner: SignedUpMember) -> dict[str, Any]:
    (project,) = await get(owner, "projects")
    found: dict[str, Any] = project
    return found


async def snapshot(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """What the demo Organisation holds, as counts and names an interviewer would see."""
    project = await demo_project(owner)
    documents = await get(owner, "projects", project["id"], "documents")
    async with app.state.sessionmaker() as session:
        audit_events = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organisation_id == uuid.UUID(owner.organisation_id))
        )
    return {
        "members": sorted(m["email"] for m in await get(owner, "members")),
        "credentials": sorted(c["name"] for c in await get(owner, "credentials")),
        "documents": sorted((d["name"], d["edition"]) for d in documents),
        "tags": sorted(t["name"] for t in await get(owner, "projects", project["id"], "tags")),
        "agents": sorted(a["name"] for a in await get(owner, "projects", project["id"], "agents")),
        "audit_events": audit_events,
    }


# What the seed builds


async def test_the_seed_builds_the_demo_organisation_through_the_api(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    report = await seed(demo_app, ASSETS)

    owner = await signed_in(new_client, content.OWNER)
    assert owner.organisation_id == report.organisation_id
    assert owner.organisation_name == "Northwind Traders"
    members = {m["email"]: m["role"] for m in await get(owner, "members")}
    assert members == {"owner@northwind.example": "owner", "editor@northwind.example": "editor"}

    project = await demo_project(owner)
    assert project["name"] == "Northwind Handbook"
    tags = {t["name"]: t for t in await get(owner, "projects", project["id"], "tags")}
    assert {name: tag["document_count"] for name, tag in tags.items()} == {
        "HR": 1,
        "Products": 3,
    }
    documents = {d["name"]: d for d in await get(owner, "projects", project["id"], "documents")}
    assert {name: [t["name"] for t in d["tags"]] for name, d in documents.items()} == {
        "northwind-staff-handbook.md": ["HR"],
        "northwind-returns-policy.md": ["Products"],
        "northwind-product-faq.docx": ["Products"],
        "northwind-spring-range.pptx": ["Products"],
    }
    assert {d["status"] for d in documents.values()} == {"ready"}
    assert all(d["chunk_count"] > 0 for d in documents.values())

    deck = documents["northwind-spring-range.pptx"]
    deck_chunks = await get(owner, "projects", project["id"], "documents", deck["id"], "chunks")
    slides = {c["heading_path"][0]: c["text"] for c in deck_chunks["items"]}
    assert slides["Wildflower honey from Crete"] == (
        "- Raw, unfiltered honey from thyme and wildflower meadows. Sold in 250 g jars."
    )

    agents = {a["name"]: a for a in await get(owner, "projects", project["id"], "agents")}
    assert set(agents) == {"HR helper", "Product FAQ"}
    assert agents["HR helper"]["draft"]["retrieval"]["tag_ids"] == [tags["HR"]["id"]]
    assert agents["Product FAQ"]["draft"]["retrieval"]["tag_ids"] == [tags["Products"]["id"]]
    assert agents["Product FAQ"]["draft"]["experience"]["greeting"] == (
        "Hello! Ask me about our products, delivery or returns."
    )

    theme = await get(owner, "theme")
    assert theme["colours"]["primary"] == {"light": "#3f5f2a", "dark": "#a3c585"}
    assert theme["font"] == "Lora"
    assert theme["radius"] == 6


async def test_one_document_has_a_planted_injection_in_a_footnote(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    await seed(demo_app, ASSETS)
    owner = await signed_in(new_client, content.OWNER)
    project = await demo_project(owner)
    documents = {d["name"]: d for d in await get(owner, "projects", project["id"], "documents")}

    planted = []
    for document in documents.values():
        chunks = await get(owner, "projects", project["id"], "documents", document["id"], "chunks")
        planted += [
            (document["name"], c["text"]) for c in chunks["items"] if INJECTION in c["text"].lower()
        ]

    ((name, chunk),) = planted
    assert name == "northwind-returns-policy.md"
    assert "NWT-FREE-50" in chunk


def test_the_seed_content_is_synthetic_and_freely_licensed() -> None:
    licence = (ASSETS / "LICENCE.md").read_text()
    assert "CC0 1.0" in licence
    assert "synthetic" in licence
    for document in content.DOCUMENTS:
        assert (ASSETS / "documents" / document.filename).is_file()
        assert document.filename in licence


async def test_the_owner_and_editor_sign_in_with_the_printed_details(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    report = await seed(demo_app, ASSETS)

    printed = "\n".join(report.lines())
    assert "owner@northwind.example  password: northwind-owner-demo" in printed
    assert "editor@northwind.example  password: northwind-editor-demo" in printed
    assert "Studio: https://studio.example.test/" in printed
    assert "Default Model: Demo model (Northwind demo model)" in printed
    assert "4 Documents" in printed
    editor = await signed_in(new_client, content.EDITOR)
    assert editor.organisation_id == report.organisation_id
    session = await editor.client.get("/api/auth/me")
    assert session.status_code == 200, session.text
    (membership,) = session.json()["organisations"]
    assert membership["role"] == "editor"


async def test_the_demo_model_is_labelled_and_answers_without_any_api_key(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    await seed(demo_app, ASSETS)
    editor = await signed_in(new_client, content.EDITOR)

    (credential,) = await get(editor, "credentials")
    assert (credential["name"], credential["provider"]) == ("Northwind demo model", "demo")
    default = await get(editor, "default-model")
    assert (default["provider"], default["model"], default["model_name"]) == (
        "demo",
        "demo-chat",
        "Demo model",
    )
    providers = await editor.client.get("/api/providers")
    (demo,) = [p for p in providers.json() if p["id"] == "demo"]
    assert demo["name"] == "Demo (not a real model)"

    project = await demo_project(editor)
    agents = {a["name"]: a for a in await get(editor, "projects", project["id"], "agents")}
    agent_id = agents["Product FAQ"]["id"]
    conversation = await start_conversation(editor, project["id"], agent_id)
    response = await ask(
        editor, project["id"], agent_id, conversation["id"], "Can I return a jar of honey?"
    )

    assert response.status_code == 200, response.text
    answer = "".join(data["text"] for kind, data in parse_sse(response.text) if kind == "token")
    assert answer.startswith("Demo model (canned answer, not AI): from northwind-")
    assert "[C1]" in answer
    (citation,) = [data for kind, data in parse_sse(response.text) if kind == "citation"]
    assert citation["label"] == "C1"
    assert answer.startswith(
        f"Demo model (canned answer, not AI): from {citation['document_name']}"
    )


# Idempotence and reset


async def test_seeding_twice_changes_nothing(demo_app: FastAPI, new_client: ClientFactory) -> None:
    first = await seed(demo_app, ASSETS)
    owner = await signed_in(new_client, content.OWNER)
    before = await snapshot(demo_app, owner)

    again = await seed(demo_app, ASSETS)

    assert again == first
    assert await snapshot(demo_app, owner) == before
    assert before["documents"] == sorted((d.filename, 1) for d in content.DOCUMENTS)


async def test_seeding_again_puts_back_what_was_changed(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    await seed(demo_app, ASSETS)
    owner = await signed_in(new_client, content.OWNER)
    expected = await snapshot(demo_app, owner)
    project = await demo_project(owner)
    base = f"/api/organisations/{owner.organisation_id}"
    tags = {t["name"]: t["id"] for t in await get(owner, "projects", project["id"], "tags")}
    documents = await get(owner, "projects", project["id"], "documents")
    agents = await get(owner, "projects", project["id"], "agents")
    # Someone experiments: the Products Tag, a Document and an Agent go, the Theme changes,
    # the HR Agent loses its scoping, and a new credential becomes the Default Model.
    edits = [
        await owner.client.delete(f"{base}/projects/{project['id']}/tags/{tags['Products']}"),
        await owner.client.delete(
            f"{base}/projects/{project['id']}/documents/{documents[0]['id']}"
        ),
        await owner.client.put(f"{base}/theme", json={**await get(owner, "theme"), "radius": 0}),
    ]
    hr = next(a for a in agents if a["name"] == "HR helper")
    draft = {**hr["draft"], "retrieval": {**hr["draft"]["retrieval"], "tag_ids": []}}
    edits.append(
        await owner.client.put(
            f"{base}/projects/{project['id']}/agents/{hr['id']}/draft", json=draft
        )
    )
    other = await owner.client.post(
        f"{base}/credentials",
        json={"name": "Experiment", "provider": "openai", "api_key": "sk-experiment-0000"},
    )
    edits.append(
        await owner.client.put(
            f"{base}/default-model",
            json={"credential_id": other.json()["id"], "model": "gpt-4.1-mini"},
        )
    )
    assert [e.status_code for e in edits] == [204, 204, 200, 200, 200]

    await seed(demo_app, ASSETS)

    after = await snapshot(demo_app, owner)
    assert after["credentials"] == sorted([*expected["credentials"], "Experiment"])
    assert {k: v for k, v in after.items() if k not in ("credentials", "audit_events")} == {
        k: v for k, v in expected.items() if k not in ("credentials", "audit_events")
    }
    assert (await get(owner, "default-model"))["model"] == "demo-chat"
    assert (await get(owner, "theme"))["radius"] == 6
    agents = await get(owner, "projects", project["id"], "agents")
    hr = next(a for a in agents if a["name"] == "HR helper")
    assert hr["draft"]["retrieval"]["tag_ids"] == [tags["HR"]]


async def test_reset_recreates_only_the_demo_organisation(
    demo_app: FastAPI, new_client: ClientFactory, tenant_factory: TenantFactory
) -> None:
    bystander = await tenant_factory()
    made = await bystander.client.post(
        f"/api/organisations/{bystander.organisation_id}/projects", json={"name": "Not the demo"}
    )
    assert made.status_code == 201, made.text
    first = await seed(demo_app, ASSETS)
    owner = await signed_in(new_client, content.OWNER)
    seeded = await snapshot(demo_app, owner)
    # Someone tries the demo first: a Playground Conversation, with its Messages and Trace.
    project = await demo_project(owner)
    (agent, *_) = await get(owner, "projects", project["id"], "agents")
    conversation = await start_conversation(owner, project["id"], agent["id"])
    asked = await ask(owner, project["id"], agent["id"], conversation["id"], "How much leave?")
    assert asked.status_code == 200, asked.text
    store = demo_app.state.ingestion.object_store
    assert isinstance(store, InMemoryObjectStore)
    demo_files = {
        k for k in store.objects if k.startswith(f"organisations/{first.organisation_id}")
    }
    assert len(demo_files) == 2 * len(content.DOCUMENTS)  # originals and converted markdown
    async with demo_app.state.sessionmaker() as session:
        bystander_events = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organisation_id == uuid.UUID(bystander.organisation_id))
        )

    second = await reset(demo_app, ASSETS)

    assert second.organisation_id != first.organisation_id
    # The old demo accounts' sessions ended with them.
    assert (await owner.client.get("/api/auth/me")).status_code == 401
    owner = await signed_in(new_client, content.OWNER)
    assert owner.organisation_id == second.organisation_id
    recreated = await snapshot(demo_app, owner)
    assert {k: v for k, v in recreated.items() if k != "audit_events"} == {
        k: v for k, v in seeded.items() if k != "audit_events"
    }
    assert recreated["audit_events"] > 0
    assert not {k for k in store.objects if k.startswith(f"organisations/{first.organisation_id}")}
    async with demo_app.state.sessionmaker() as session:
        old_events = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organisation_id == uuid.UUID(first.organisation_id))
        )
        assert old_events == 0
        assert bystander_events == await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organisation_id == uuid.UUID(bystander.organisation_id))
        )
    projects = await bystander.client.get(
        f"/api/organisations/{bystander.organisation_id}/projects"
    )
    assert [p["name"] for p in projects.json()] == ["Not the demo"]


async def test_reset_with_no_demo_organisation_just_seeds(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    report = await reset(demo_app, ASSETS)

    owner = await signed_in(new_client, content.OWNER)
    assert owner.organisation_id == report.organisation_id


async def test_audit_events_stay_append_only_outside_an_erasure(
    demo_app: FastAPI, owner: SignedUpMember
) -> None:
    async with demo_app.state.sessionmaker() as session:
        await session.execute(
            text("SELECT set_config('app.erasing_organisation', :id, true)"),
            {"id": str(uuid.uuid4())},  # erasing some other Organisation
        )
        with pytest.raises(Exception, match="append-only: DELETE is not allowed"):
            await session.execute(
                text("DELETE FROM audit_events WHERE organisation_id = :id"),
                {"id": owner.organisation_id},
            )


async def test_reset_refuses_while_a_demo_account_belongs_to_another_organisation(
    demo_app: FastAPI, new_client: ClientFactory, tenant_factory: TenantFactory
) -> None:
    first = await seed(demo_app, ASSETS)
    other = await tenant_factory()
    editor = await signed_in(new_client, content.EDITOR)
    invited = await other.client.post(
        f"/api/organisations/{other.organisation_id}/invites",
        json={"email": content.EDITOR.email, "role": "editor", "send_email": False},
    )
    token = invited.json()["link"].split("token=", 1)[1]
    accepted = await editor.client.post("/api/invites/accept", json={"token": token})
    assert accepted.status_code == 200, accepted.text

    with pytest.raises(SeedError, match=r"editor@northwind\.example belongs to another"):
        await reset(demo_app, ASSETS)

    owner = await signed_in(new_client, content.OWNER)
    assert owner.organisation_id == first.organisation_id  # nothing was erased

    # Once the Editor has left the other Organisation, reset works. That Organisation's Audit
    # Events still name the old Editor, so their account is retired rather than deleted.
    removed = await other.client.delete(
        f"/api/organisations/{other.organisation_id}/members/{editor.member_id}"
    )
    assert removed.status_code == 204, removed.text
    second = await reset(demo_app, ASSETS)

    new_editor = await signed_in(new_client, content.EDITOR)
    assert new_editor.organisation_id == second.organisation_id
    assert new_editor.member_id != editor.member_id
    events = await other.client.get(f"/api/organisations/{other.organisation_id}/audit-events")
    actors = {e["actor"]["id"] for e in events.json()["items"] if e["actor"] is not None}
    assert editor.member_id in actors


# A real credential, optionally


async def test_a_real_credential_can_answer_instead_of_the_demo_model(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    real = RealCredential(Provider.OPENAI, "sk-real-key-from-env-0000", "gpt-4.1")

    report = await seed(demo_app, ASSETS, real)
    again = await seed(demo_app, ASSETS, real)

    owner = await signed_in(new_client, content.OWNER)
    credentials = {c["name"]: c for c in await get(owner, "credentials")}
    assert set(credentials) == {"Northwind demo model", "Northwind OpenAI"}
    assert credentials["Northwind OpenAI"]["masked_suffix"] == "0000"
    default = await get(owner, "default-model")
    assert (default["credential_name"], default["model"]) == ("Northwind OpenAI", "gpt-4.1")
    assert report.default_model == again.default_model == "GPT-4.1 (Northwind OpenAI)"


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, None),
        ({"SEED_CREDENTIAL_PROVIDER": " ", "SEED_CREDENTIAL_API_KEY": ""}, None),
        (
            {"SEED_CREDENTIAL_PROVIDER": "Anthropic", "SEED_CREDENTIAL_API_KEY": " sk-ant-1 "},
            RealCredential(Provider.ANTHROPIC, "sk-ant-1", "claude-haiku-4-5"),
        ),
        (
            {"SEED_CREDENTIAL_PROVIDER": "openai", "SEED_CREDENTIAL_API_KEY": "sk-1"},
            RealCredential(Provider.OPENAI, "sk-1", "gpt-4.1-mini"),
        ),
        (
            {
                "SEED_CREDENTIAL_PROVIDER": "openai",
                "SEED_CREDENTIAL_API_KEY": "sk-1",
                "SEED_CREDENTIAL_MODEL": "gpt-4o-mini",
            },
            RealCredential(Provider.OPENAI, "sk-1", "gpt-4o-mini"),
        ),
    ],
)
def test_a_real_credential_is_read_from_the_environment(
    environ: dict[str, str], expected: RealCredential | None
) -> None:
    assert real_credential_from_env(environ) == expected


@pytest.mark.parametrize(
    "environ",
    [
        {"SEED_CREDENTIAL_PROVIDER": "openai"},
        {"SEED_CREDENTIAL_API_KEY": "sk-1"},
        {"SEED_CREDENTIAL_PROVIDER": "voyage", "SEED_CREDENTIAL_API_KEY": "pa-1"},
    ],
)
def test_a_half_set_or_unusable_real_credential_is_refused(environ: dict[str, str]) -> None:
    with pytest.raises(SeedError, match="Set both SEED_CREDENTIAL_PROVIDER"):
        real_credential_from_env(environ)


# When the seed can't go on


async def test_the_seed_stops_if_the_demo_owners_email_has_another_password(
    demo_app: FastAPI, client: httpx.AsyncClient
) -> None:
    taken = await client.post(
        "/api/auth/sign-up",
        json={
            "name": "Someone",
            "email": content.OWNER.email,
            "password": "a different password",
            "organisation_name": "Northwind Traders",
        },
    )
    assert taken.status_code == 201, taken.text

    with pytest.raises(SeedError, match=r"Can't sign in as the demo Owner .*seed-reset"):
        await seed(demo_app, ASSETS)


async def test_the_seed_stops_if_the_demo_owner_has_no_demo_organisation(
    demo_app: FastAPI, client: httpx.AsyncClient
) -> None:
    taken = await client.post(
        "/api/auth/sign-up",
        json={
            "name": "Someone",
            "email": content.OWNER.email,
            "password": content.OWNER.password,
            "organisation_name": "Somewhere else",
        },
    )
    assert taken.status_code == 201, taken.text

    with pytest.raises(SeedError, match="owns no Organisation named 'Northwind Traders'"):
        await seed(demo_app, ASSETS)

    # Not a demo Organisation, so reset leaves it alone and refuses; clear it up by hand.
    with pytest.raises(SeedError, match=r"owner@northwind\.example belongs to another"):
        await reset(demo_app, ASSETS)
    async with demo_app.state.sessionmaker() as session:
        member_id = uuid.UUID(taken.json()["member"]["id"])
        (organisation,) = taken.json()["organisations"]
        await erase_organisation(
            session, demo_app.state.ingestion.object_store, uuid.UUID(organisation["id"])
        )
        await erase_member(session, member_id)


async def test_an_api_refusal_stops_the_seed_with_the_reason(
    demo_app: FastAPI, new_client: ClientFactory
) -> None:
    await seed(demo_app, ASSETS)
    owner = await signed_in(new_client, content.OWNER)
    editor = await signed_in(new_client, content.EDITOR)
    base = f"/api/organisations/{owner.organisation_id}"
    removed = await owner.client.delete(f"{base}/members/{editor.member_id}")
    assert removed.status_code == 204, removed.text

    # The Editor's account still exists, so signing up with the invite is refused.
    with pytest.raises(SeedError, match=r"POST /api/invites/sign-up answered 409"):
        await seed(demo_app, ASSETS)


# Through RustFS, and from the command line


@pytest.fixture
async def rustfs_app(
    settings_env: pytest.MonkeyPatch, database_schema: None
) -> AsyncIterator[FastAPI]:
    settings_env.setenv("OBJECT_STORE", "s3")
    settings_env.setenv("OBJECT_STORE_BUCKET", f"test-{uuid.uuid4().hex[:12]}")
    settings_env.setenv("OBJECT_STORE_CREATE_BUCKET", "true")
    settings_env.setenv("OBJECT_STORE_ENDPOINT_URL", RUSTFS_URL)
    settings_env.setenv("OBJECT_STORE_ACCESS_KEY_ID", RUSTFS_KEYS["access_key_id"])
    settings_env.setenv("OBJECT_STORE_SECRET_ACCESS_KEY", RUSTFS_KEYS["secret_access_key"])
    application = create_app()
    async with LifespanManager(application):
        await erase_demo(application)
        yield application


async def test_files_go_to_the_object_store_through_presigned_urls(rustfs_app: FastAPI) -> None:
    report = await seed(rustfs_app, ASSETS)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=rustfs_app), base_url=BASE_URL
    ) as client:
        signed_in = await client.post(
            "/api/auth/sign-in",
            json={"email": content.OWNER.email, "password": content.OWNER.password},
        )
        assert signed_in.status_code == 200, signed_in.text
        base = f"/api/organisations/{report.organisation_id}"
        (project,) = (await client.get(f"{base}/projects")).json()
        documents = (await client.get(f"{base}/projects/{project['id']}/documents")).json()
    # Ingestion read each file back from RustFS, where the seed's PUT left it.
    assert {d["status"] for d in documents} == {"ready"}
    assert len(documents) == len(content.DOCUMENTS)


def test_the_command_seeds_resets_and_prints_the_sign_in_details(
    settings_env: pytest.MonkeyPatch, database_schema: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--reset", "--assets", str(ASSETS)]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out

    assert "Seeded the demo Organisation 'Northwind Traders'." in first
    assert "owner@northwind.example  password: northwind-owner-demo" in first
    assert second.splitlines()[-6:] == first.splitlines()[-6:]


def test_the_command_reports_why_it_failed(
    settings_env: pytest.MonkeyPatch, database_schema: None, capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env.setenv("SEED_CREDENTIAL_PROVIDER", "openai")

    assert main([]) == 1
    assert "Seed failed: Set both SEED_CREDENTIAL_PROVIDER" in capsys.readouterr().err
