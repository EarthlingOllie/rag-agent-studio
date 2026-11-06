"""Helpers for uploading Theme images through the API, as the Studio does, and tiny images."""

import struct
import zlib
from typing import Any

import httpx

from tests.conftest import SignedUpMember
from tests.documents import app_of, put_to_memory_store


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(red: int = 79, green: int = 70, blue: int = 229) -> bytes:
    """A real 1x1 PNG of one colour."""
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(bytes([0, red, green, blue]))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", pixels)
        + _chunk(b"IEND", b"")
    )


# The leading bytes that identify each format; enough for the API's type check.
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(64)
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + bytes(64)


def images_path(member: SignedUpMember, kind: str) -> str:
    return f"/api/organisations/{member.organisation_id}/theme/images/{kind}"


async def start(member: SignedUpMember, kind: str, filename: str, size: int) -> httpx.Response:
    return await member.client.post(
        f"{images_path(member, kind)}/uploads", json={"filename": filename, "size_bytes": size}
    )


async def put_file(member: SignedUpMember, ticket: dict[str, Any], data: bytes) -> None:
    """The browser's PUT to the presigned URL (the in-memory store in tests)."""
    await put_to_memory_store(app_of(member), ticket["url"], data, ticket["content_type"])


async def confirm(member: SignedUpMember, kind: str, upload_id: str) -> httpx.Response:
    return await member.client.put(images_path(member, kind), json={"upload_id": upload_id})


async def uploaded_ticket(
    member: SignedUpMember, kind: str, data: bytes, filename: str = "brand.png"
) -> dict[str, Any]:
    """Starts an upload and PUTs the file, without confirming it."""
    started = await start(member, kind, filename, len(data))
    assert started.status_code == 201, started.text
    ticket: dict[str, Any] = started.json()
    await put_file(member, ticket, data)
    return ticket


async def upload(
    member: SignedUpMember, kind: str, data: bytes, filename: str = "brand.png"
) -> dict[str, Any]:
    """Presign, PUT, confirm; returns the Theme the confirmation answers with."""
    ticket = await uploaded_ticket(member, kind, data, filename)
    confirmed = await confirm(member, kind, ticket["upload_id"])
    assert confirmed.status_code == 200, confirmed.text
    theme: dict[str, Any] = confirmed.json()
    return theme
