# Evidence: ticket 23-01, spike `terraform apply` on Floci

The spike ran on 2026-11-27 in the x86_64 sandbox (4 vCPU, 15.7 GB, Docker 29.9.3) against Floci 2.5.0. Its code (a copy of `infra/` with a scratch `local` environment, the run scripts and the memory scripts) stayed outside the repository; only these trimmed logs and the corrected documents are committed. The ticket's Evidence section explains each one.

| File | What it is |
|---|---|
| [isolation.log](isolation.log) | Before any apply: from the internal Docker network the terraform container used, AWS hosts do not resolve and Floci answers |
| [apply-rounds.log](apply-rounds.log) | The errors of each apply round, from the unchanged demo inputs to the run that reached the end, and the S3 Control call that hung the first round |
| [prefix-list-and-ami.log](prefix-list-and-ami.log) | The CloudFront prefix list and the fck-nat AMI lookups, against a Floci without the catalog and the spike's Floci with it |
| [plan-after-apply.log](plan-after-apply.log) | The second `terraform plan` after the apply: the drift the emulator causes |
| [ecs.log](ecs.log) | Services, capacity provider strategies, the ARM64 refusal, a FARGATE_SPOT task, the task protection API and the task's environment |
| [data-plane.log](data-plane.log) | The cache and database endpoints, pgvector in the emulated RDS, the cache's TLS certificate, the ECR auth token's endpoint |
| [cloudfront.log](cloudfront.log) | The distribution serving the static bucket and forwarding `/api/*` to the load balancer; deep links |
| [autoscaling.log](autoscaling.log) | Scalable targets, policies and alarms; queue-depth alarms with and without metric math; the API's CPU policy fed by `put-metric-data` |
| [memory.log](memory.log) | The Floci side's memory, one general-pool worker process ingesting the seed Documents, and the API process with its local models |
| [destroy.log](destroy.log) | `terraform destroy` of the whole environment |
