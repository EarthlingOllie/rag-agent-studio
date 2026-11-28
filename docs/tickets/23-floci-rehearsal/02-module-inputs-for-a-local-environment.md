# 02: Module inputs for a local environment

**Ticket:** `23-02` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** The modules gain the few inputs a local environment needs to differ from the demo, so no module ever branches on "is this local". The demo environment's plan is unchanged.

**Blocked by:**
- `23-01`

**Status:** done

- [x] Compute: the CPU architecture of every task definition, and extra environment variables for the services; the image repository URL's validation also accepts the emulator's path-style registry (`localhost:<port>/<12 digits>/<region>/<repo>`), as 23-01 found it refuses it
- [x] Database: the port (23-01 found `storage_type` reads back unchanged, so it needs no input)
- [x] KMS: the rotation period may be left unset; cache: the maintenance window may be left unset (23-01 found the emulator reads back 0 and stores no window, so a second plan shows changes)
- [x] CDN: optional custom error responses, the distribution's domain as an output, and the origin's address as an input the environment can override; the `.elb.amazonaws.com` validation applies to the load balancer's name only when no override is given, and the override accepts `localhost`
- [x] Every new input defaults to today's value; a `terraform test` asserts the demo environment's plan is the same with the defaults
- [x] `terraform test` asserts each input reaches the resources it should and nothing else
- [x] `make infra-check` passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## Evidence

Every run below is a `terraform test` run at the module seam (mocked AWS provider, nothing applied anywhere real). [infra-check.log](23-02-evidence/infra-check.log): `make infra-check` exits 0 with these changes (bootstrap 11 runs, demo 10, cache 22, cdn 31, database 25, ecs 92, kms 14; TFLint clean; Checkov 275 passed, 0 failed).

### Compute (`infra/modules/ecs`)

- `cpu_architecture` (`ARM64` default, or `X86_64`) reaches all six task definitions: the four services, the migration and the seed task (`cpu_architecture_reaches_every_task_definition`, `cpu_architecture_defaults_to_arm64_everywhere`, `rejects_an_unknown_cpu_architecture`). The module reports it as output `cpu_architecture`, read back from the task definitions.
- `extra_environment` (map, default `{}`) adds plain variables to every container's environment and to the `task_environment` output, never to the secrets, and leaves every other setting as it was: the run compares against the defaults run's `task_environment` (`extra_environment_reaches_every_container_and_nothing_else`, `no_extra_environment_by_default`). A name that would replace one of the module's settings (for example `REDIS_TLS`) fails a precondition (`rejects_extra_environment_that_overrides_a_module_setting`); a name that is not an environment variable name fails validation.
- `image_repository_url` also accepts the emulator's path-style registry `localhost:<port>/<12 digits>/<region>/<repo>`, and the services then run that image (`accepts_the_emulators_path_style_registry`); a `localhost` URL without account and region, a path-style URL on another host and a Docker Hub image are still refused.

### Database (`infra/modules/database`)

- `port` (default 5432, 1150-65535) reaches the instance, the `port` output and every client ingress rule (`the_port_reaches_the_instance_and_the_ingress_rules`, `rejects_a_port_rds_does_not_allow`). No `storage_type` input (23-01: it reads back unchanged).

### KMS and cache

- `rotation_period_in_days` may be null: rotation stays on and the module sets no period, so the key reports whatever the service stores (the mock stands in for Floci's 0) (`the_rotation_period_may_be_left_unset`); the default stays 365 (`the_rotation_period_is_set_by_default`). New output `rotation_period_in_days` per key.
- `maintenance_window` may be null and is then left to the service (`the_maintenance_window_may_be_left_unset`); default `sun:03:30-sun:04:30` (`the_maintenance_window_is_set_by_default`); a malformed window is refused. New output `maintenance_window`.

### CDN (`infra/modules/cdn`)

- `custom_error_responses` (default `[]`) reach the distribution only when given (`custom_error_responses_appear_only_when_given`; the existing `a_function_gives_the_studio_spa_fallback_routing` asserts none by default). New output `custom_error_responses`.
- New output `distribution_domain_name`: the distribution's own domain even when a custom domain is set (`outputs_the_distributions_own_domain_even_with_a_custom_one`).
- `api_origin_domain` (default null) overrides the API origin and accepts `localhost`; it changes that origin and nothing else, and output `api_origin_domain` follows it (`the_api_origin_can_be_overridden`, `the_api_origin_defaults_to_the_alb`). The `.elb.amazonaws.com` check on `alb_dns_name` applies only without the override (the override run passes Floci's `...elb.floci` name; `rejects_an_origin_that_is_not_an_alb` still fails without it), and a scheme or port in the override is refused.

### The demo is unchanged

The demo environment passes none of the new inputs. `infra/envs/demo/tests/demo.tftest.hcl` `the_local_environment_inputs_leave_the_demo_unchanged` checks, through each module's outputs, the pre-23-02 values: ARM64 everywhere, exactly the module's environment variables in each of the six containers (the full name list), database port 5432 everywhere, both keys rotating every 365 days, the Sunday maintenance window, no custom error response and the ALB as the API origin.

### Coverage, glossary, ADRs

Terraform has no line-coverage tool; every new input, output and validation has a run (above), and the backend and frontend are untouched, so their 100% holds. No new domain term (module inputs are infrastructure, which the glossary does not cover). No ADR changes: no decision changed, only inputs with the old values as defaults. `docs/development.md` has a paragraph for this ticket.

## Gaps and best guesses

- **Deferred to 23-03/23-04:** that these inputs really remove the four drifts in Floci (a second plan with no changes) is checked against the emulator by 23-04's wrapper; here it is shown only at the module seam with mocks. The demo's plan is shown unchanged through module outputs, not by planning against real AWS state (no AWS access).
- **`extra_environment` reaches the migration and seed tasks too**, not only the four services: they connect to the same database, cache and queues and so need the same CA setting (`SSL_CERT_FILE`). "Nothing else" is read as: no secret, no other setting, no other resource.
- **Override, not replace:** extra variables may only add; overriding a module setting (for example turning `REDIS_TLS` off) is refused, so a local environment can't quietly weaken what the modules promise.
- **Read-back outputs** (`cpu_architecture`, `rotation_period_in_days`, `maintenance_window`, `custom_error_responses`) were added so the demo test can check the defaults: `terraform test` cannot read a child module's resources. They report what the resources hold, not the inputs.
- **The emulator registry check is narrow on purpose:** only `localhost:<port>/<account>/<region>/<repo>`, the form 23-01 saw with `ECR_URI_STYLE=path`.
- **Checkov's count fell from 277 to 275 passed, still 0 failed:** Checkov no longer evaluates CKV_AWS_334 and CKV_AWS_335 on the demo's migration task definition, whose environment is now built through a `for` expression over `extra_environment` that its renderer does not resolve; the same checks still pass on the ecs module itself, and one CloudFront check (CKV2_AWS_72) is now reported as passed because the API origin is a `coalesce` Checkov does not resolve (the origin is still HTTP to the ALB, by design, ADR-0011).
