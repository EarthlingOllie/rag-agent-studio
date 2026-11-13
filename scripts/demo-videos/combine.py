"""Joins the nine story videos in docs/demo into one, with a title card before each story.

    python3 scripts/demo-videos/combine.py

Run it after encode.sh. Each card's title and user story come from docs/demo.md (its
"## N. Title" heading and the "> As a ..." quote under it), so the cards follow the page.
Writes docs/demo/all-stories.mp4 and its poster, docs/demo/all-stories.jpg. Needs ffmpeg and Pillow.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "docs" / "demo"
SIZE = (1280, 800)
FPS = 25
INTRO_SECONDS = 4.5
CARD_SECONDS = 4.0
FADE = 0.4

BACKGROUND = "#0f172a"
TEXT = "#f8fafc"
MUTED = "#cbd5e1"
ACCENT = "#5eead4"

FONT_DIRS = [
    Path("/usr/share/fonts/opentype/inter"),
    Path("/Library/Fonts"),
    Path.home() / "Library/Fonts",
]
STORY = re.compile(
    r"^## (\d+)\. (.+?)\n\n> (.+?)\n\n\[!\[[^\]]*\]\(demo/([\w-]+)\.jpg\)", re.M | re.S
)


def font(weight: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for directory in FONT_DIRS:
        path = directory / f"Inter-{weight}.otf"
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def stories() -> list[tuple[str, str, str]]:
    """(slug, title, user story) for each story, in docs/demo.md's order."""
    text = (ROOT / "docs" / "demo.md").read_text()
    found = []
    for match in STORY.finditer(text):
        number, title, story, slug = match.groups()
        found.append((slug, f"{number}. {title}", " ".join(story.split())))
    if len(found) != 9:
        sys.exit(f"Expected nine stories in docs/demo.md, found {len(found)}.")
    return found


def card(path: Path, kicker: str, title: str, body: str) -> None:
    image = Image.new("RGB", SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    left, width = 120, SIZE[0] - 240
    title_font, body_font, kicker_font = font("Bold", 56), font("Regular", 30), font("SemiBold", 26)
    title_lines = textwrap.wrap(title, 34)
    body_lines = textwrap.wrap(body, 62)
    height = 40 + len(title_lines) * 70 + 36 + len(body_lines) * 44
    y = (SIZE[1] - height) // 2
    draw.text((left, y), kicker.upper(), font=kicker_font, fill=ACCENT)
    y += 56
    for line in title_lines:
        draw.text((left, y), line, font=title_font, fill=TEXT)
        y += 70
    y += 20
    draw.rectangle((left, y, left + 64, y + 4), fill=ACCENT)
    y += 32
    for line in body_lines:
        draw.text((left, y), line, font=body_font, fill=MUTED)
        y += 44
    widest = max(draw.textlength(line, font=body_font) for line in body_lines)
    if y > SIZE[1] - 40 or widest > width:
        sys.exit(f"The card for {title!r} doesn't fit: shorten its text.")
    image.save(path)


def tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        sys.exit(f"{name} is not installed.")
    return path


def ffmpeg(*args: str) -> None:
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", *args], check=True)  # noqa: S603


def card_clip(png: Path, seconds: float, out: Path) -> None:
    fades = f"fade=t=in:st=0:d={FADE},fade=t=out:st={seconds - FADE}:d={FADE}"
    ffmpeg(
        "-loop",
        "1",
        "-t",
        str(seconds),
        "-i",
        str(png),
        "-vf",
        f"fps={FPS},format=yuv420p,{fades}",
        "-c:v",
        "libx264",
        "-crf",
        "28",
        str(out),
    )


def main() -> None:
    found = stories()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        parts = []
        card(
            work / "intro.png",
            "RAG Agent Studio · demo",
            "Nine core user stories",
            "From signing up and building a Knowledge Base to publishing, embedding, "
            "measuring and defending an AI Agent. Every step runs against the seeded stack "
            "and is answered by the labelled demo model.",
        )
        card_clip(work / "intro.png", INTRO_SECONDS, work / "intro.mp4")
        parts.append(work / "intro.mp4")
        for index, (slug, title, story) in enumerate(found, start=1):
            kicker = f"Story {index} of {len(found)}"
            card(work / f"{slug}.png", kicker, title.split(". ", 1)[1], story)
            card_clip(work / f"{slug}.png", CARD_SECONDS, work / f"{slug}-card.mp4")
            parts += [work / f"{slug}-card.mp4", DEMO / f"{slug}.mp4"]
        inputs = [arg for part in parts for arg in ("-i", str(part))]
        normalise = f"fps={FPS},scale={SIZE[0]}:{SIZE[1]},setsar=1,format=yuv420p"
        streams = "".join(f"[{i}:v]{normalise}[v{i}];" for i in range(len(parts)))
        joined = "".join(f"[v{i}]" for i in range(len(parts)))
        out = DEMO / "all-stories.mp4"
        ffmpeg(
            *inputs,
            "-filter_complex",
            f"{streams}{joined}concat=n={len(parts)}:v=1:a=0[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-crf",
            "28",
            "-preset",
            "slow",
            "-movflags",
            "+faststart",
            "-an",
            str(out),
        )
        Image.open(work / "intro.png").resize((640, 400)).save(DEMO / "all-stories.jpg", quality=85)
    seconds = float(
        subprocess.run(  # noqa: S603
            [
                tool("ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    length = f"{int(seconds // 60)}:{int(seconds % 60):02d}"
    print(f"{out.relative_to(ROOT)}: {length}, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
