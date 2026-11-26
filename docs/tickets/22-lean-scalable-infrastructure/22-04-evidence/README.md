# Evidence: ticket 22-04, two worker pools

Committed in place on the session branch. The work is in `infra/modules/ecs/` (four services, capacity providers, `worker_spot`, stop timeout, per-pool task roles, the seed role's queue permission, `task-settings.json`), `infra/envs/demo/` (database and cache admit both pools, `worker_spot` passed through), `scripts/deploy/deploy.sh` (rolls every service, reports each stable) and `backend/tests/unit/test_aws_task_settings.py`. The ticket's Evidence section maps each criterion to its tests.

| File | What it is |
|---|---|
| [infra-check.log](infra-check.log) | A full `make infra-check` run after the change: exit 0, ecs 69 runs, demo 9, TFLint clean, Checkov 273 passed and 0 failed, the deploy-script shell tests and the node coverage gate |
| [tdd-red-terraform.log](tdd-red-terraform.log) | The failing `terraform test` runs written first: the ecs suite before the pools and capacity providers, the demo suite before the wiring, and the ecs default-size run before the runs pool was resized to 6 GB |
| [tdd-red-deploy.log](tdd-red-deploy.log) | `deploy.test.sh` before the script change: `deploy.sh` stopped on a jq compile error reading `.services.worker-general` |
| [run-memory.py](run-memory.py) | The script that measured one runs-pool worker process doing a Run's model work on the local models |
| [run-memory.log](run-memory.log) | Its output, and the memory of a real `--concurrency=2` runs-pool worker tree after warm-up |

## Runs pool memory

A Run's model work on the local models (`EMBEDDER=local`, `INPUT_CLASSIFIER=local`, `INJECTION_CLASSIFIER=local`; the model gateway was the offline fake) was measured on 2026-11-26 in the x86_64 sandbox:

- The worker app imported, as `celery -A app.worker.main` does: about 0.32 GB RSS.
- After the warm-up each pool process runs after the fork (it loads the Guardrail classifier, a DeBERTa-v3 ONNX model): about 1.48 GB.
- Doing a Run's model work (a query embedding with the local Embedding Model and an input-Guardrail classification of a question and an answer per case): 2.35 GB by the 20th case, flat to the 120th.
- The real worker tree (`--concurrency=2 --queues=<runs queue>`) after warm-up: a Celery parent of 0.22 GB PSS and two pool processes of 1.42 and 1.32 GB PSS.

Two pool processes at their peak plus the parent come to about 4.7 GB, past the spec's planned 4 GB. The default `worker-runs` size is therefore 1 vCPU / 6 GB (Fargate allows 2 to 8 GB at 1 vCPU), still below the general pool's 8 GB.

Deferred: behaviour in a real AWS account (ticket 22-09).
