"""What one runs-pool worker process holds at its peak: the worker app imported (as
`celery -A app.worker.main` does), the warm-up after fork (the Guardrail classifier), then a Run's
model work on the local models: query embeddings and input-Guardrail classifications.

Run from backend/ with the worker's settings (EMBEDDER=local, INPUT_CLASSIFIER=local,
INJECTION_CLASSIFIER=local, MODEL_GATEWAY=fake, the queue and database settings):
PYTHONPATH=. uv run python ../docs/tickets/22-lean-scalable-infrastructure/22-04-evidence/run-memory.py"""
import asyncio, resource, sys, time
sys.argv = ["celery", "worker"]
import app.worker.main  # noqa: E402,F401
from app.documents.ports import current_ports, warm_up  # noqa: E402

def rss_mb() -> float:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0

print(f"imported worker app: rss={rss_mb():.0f} MB", flush=True)
warm_up(current_ports())
print(f"after warm-up (Guardrail classifier loaded): rss={rss_mb():.0f} MB", flush=True)
classifier = current_ports().classifier
embedder = next(iter(current_ports().embedders.values()))
text = ("Please summarise the leave policy for part-time staff and say who approves carry-over. " * 30)
async def work(n: int) -> None:
    for i in range(n):
        await embedder.embed_query(f"question {i}: {text[:400]}")
        classifier.classify([text, f"answer {i} " + text])
        if i % 20 == 19:
            print(f"  case {i+1}: rss={rss_mb():.0f} MB", flush=True)

t = time.time(); asyncio.run(work(120))
print(f"after 120 Run cases (query embeddings + input-Guardrail classifications): rss={rss_mb():.0f} MB, peak={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB, {time.time()-t:.0f}s", flush=True)
