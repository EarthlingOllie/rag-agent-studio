"""``python -m app.evals``: runs the attack evaluation suite and writes its report.

Mocked mode (``make eval``, the Guardrail evaluation CI job on every PR) answers with the naive
model; live mode (``make eval-live``, the nightly job) answers with a real chat model named by
``--provider`` and ``--model``, its API key read from ``EVAL_API_KEY`` (the ``demo`` provider
needs none). Both use the production injection classifier (the local ONNX model) unless told
otherwise. Every case runs in each Retrieval Mode, Automatic and Agentic, and the report gives
each mode its verdict and Pass rate. The report is written to ``--out`` as
``attack-eval-report.json`` and ``attack-eval-report.md``, and the markdown is printed. The exit status is 0 when the report
passes in every Retrieval Mode, 1 when it fails in any, 2 when the command is used wrongly.
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import httpx2
from pydantic_ai.models import Model

from app.core.clock import SystemClock
from app.core.settings import Settings
from app.credentials.bedrock_verifier import AssumedRoleSessions, boto3_client
from app.credentials.registry import Provider
from app.evals.naive_model import naive_model
from app.evals.report import Mode, Report
from app.evals.runner import run_modes
from app.evals.suite import CASE_FILE, load_suite
from app.gateway.live import BedrockClients, LiveModelAdapters
from app.guardrails import onnx_model
from app.guardrails.classifier import InjectionClassifier
from app.guardrails.heuristic import HeuristicClassifier
from app.guardrails.local import LocalClassifier
from app.guardrails.pipeline import GuardrailPipeline

REPORT_NAME = "attack-eval-report"
LIVE_PROVIDERS = (Provider.ANTHROPIC, Provider.OPENAI, Provider.DEMO)
DEFAULT_THRESHOLD: float = Settings.model_fields["input_classifier_threshold"].default


def build_classifier(name: str, threshold: float) -> InjectionClassifier:
    """The injection classifier the pipeline runs: the local model loads on first use."""
    if name == "heuristic":
        return HeuristicClassifier()
    return LocalClassifier(onnx_model.load, threshold)


def live_chat_model(
    provider: Provider, model: str, api_key: str, client: httpx2.AsyncClient
) -> Model:
    """A real chat model, built by the model gateway's live adapters. Chat models are reached
    over HTTP, so the adapters' Bedrock clients (no STS client) are never used."""
    sessions = AssumedRoleSessions(None, SystemClock(), refresh_before=timedelta())
    bedrock = BedrockClients(sessions, partial(boto3_client, timeout_seconds=60))
    return LiveModelAdapters(client, bedrock).chat(provider, api_key, model)


def _rate(text: str) -> float:
    value = float(text)
    if not 0 <= value <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.evals", description=__doc__)
    parser.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.MOCKED.value)
    parser.add_argument("--cases", type=Path, default=CASE_FILE, help="the case file")
    parser.add_argument("--out", type=Path, default=Path("eval-report"), help="report folder")
    parser.add_argument("--classifier", choices=["local", "heuristic"], default="local")
    parser.add_argument("--threshold", type=_rate, default=DEFAULT_THRESHOLD)
    parser.add_argument("--provider", choices=[p.value for p in LIVE_PROVIDERS])
    parser.add_argument("--model", help="the live chat model")
    parser.add_argument("--min-pass-rate", type=_rate, default=0.85)
    return parser


async def _run(args: argparse.Namespace, model: Model) -> Report:
    pipeline = GuardrailPipeline(build_classifier(args.classifier, args.threshold))
    runs = await run_modes(load_suite(args.cases), pipeline, model)
    return Report(runs, Mode(args.mode), args.classifier, datetime.now(UTC), args.min_pass_rate)


async def _main(args: argparse.Namespace) -> Report:
    if args.mode == Mode.MOCKED:
        return await _run(args, naive_model())
    async with httpx2.AsyncClient(timeout=120) as client:
        model = live_chat_model(
            Provider(args.provider), args.model, os.environ.get("EVAL_API_KEY", ""), client
        )
        return await _run(args, model)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == Mode.LIVE:
        if args.provider is None or not args.model:
            parser.error("live mode needs --provider and --model")
        if args.provider != Provider.DEMO and not os.environ.get("EVAL_API_KEY"):
            parser.error(f"live mode with {args.provider} needs EVAL_API_KEY")
    report = asyncio.run(_main(args))
    args.out.mkdir(parents=True, exist_ok=True)
    markdown = report.as_markdown()
    (args.out / f"{REPORT_NAME}.json").write_text(
        json.dumps(report.as_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.out / f"{REPORT_NAME}.md").write_text(markdown, encoding="utf-8")
    sys.stdout.write(markdown)
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
