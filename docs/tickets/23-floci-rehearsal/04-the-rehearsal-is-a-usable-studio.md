# 04: The rehearsal is a usable Studio

**Ticket:** `23-04` · **Spec:** [Rehearsing the AWS deployment on Floci](../../specs/23-floci-rehearsal-spec.md)

**What to build:** After `make rehearse` and a seed, a developer can open the Studio at the rehearsal's address, sign in, upload a Document and watch it become Ready.

**Blocked by:**
- `23-03`

**Status:** ready-for-human. Every criterion but one is met and evidenced below. The deep-link criterion cannot be met as written: a 404-to-index custom error response is distribution-wide, and Floci applies it to the API's 404s too (as AWS would), which turns `/widget/a/<unknown>` and every API 404 into the Studio's HTML and fails the smoke check. A human decides between dropping the criterion (deep links stay a known gap of the rehearsal, like the CloudFront Function itself) and another approach (see the gaps).

- [x] The emulated distribution's address is the Studio URL and the uploads CORS origin in `local`
- [x] Browser uploads work: presigned links point at an address the browser can reach
- [ ] Studio deep links load after a refresh, through a 404-to-index error response that only `local` adds
- [x] Per-Visitor rate limits see the real client address: the emulator's network ranges are trusted proxies in `local`
- [x] The seed runs as a one-off task through the unchanged seed script, and the demo Owner can sign in
- [x] An uploaded Document becomes Ready, proving the worker reaches the queue, database, cache, bucket and key service by the addresses Terraform gave it
- [x] A second `terraform plan` after an apply shows no changes, and the wrapper fails if it does (23-01 found four: the database port, both KMS keys' rotation period and the cache maintenance window; 23-02's inputs remove them)
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

## How it was checked

On 2026-11-27 in the x86_64 sandbox, as in [23-03](03-make-rehearse.md#how-it-was-run): terraform and the AWS CLI on the rehearsal's tools network, dummy credentials, images built beforehand. The browser's part was played by curl from this machine ([usable.sh](23-04-evidence/usable.sh): sign in, upload through the presigned link with the CORS preflight a browser sends, wait for Ready); no browser was available. Logs: [23-04-evidence](23-04-evidence/).

## Evidence

**The distribution is the Studio URL and the uploads origin.** `local` passes its `http://<id>.cloudfront.localhost:4566` address (`local.url`) as the ecs module's `studio_url` and the storage module's `documents_cors_allowed_origin`; both modules now also accept an emulator's `http://<name>.localhost[:port]` and still refuse `http://` anywhere else (`accepts_an_emulators_localhost_studio_url`, `rejects_an_http_studio_url_with_a_port_outside_localhost`, `documents_cors_accepts_an_emulators_localhost_origin`, `rejects_an_http_origin_with_a_port_outside_localhost`; `local.tftest.hcl` `the_emulated_distribution_is_the_studio_and_the_uploads_origin`). In the run the API and workers have `STUDIO_URL=http://egyk4lut4xh5sr.cloudfront.localhost:4566` and the bucket answers the preflight with that origin ([usable-studio.log](23-04-evidence/usable-studio.log), [fresh-run.log](23-04-evidence/fresh-run.log)).

**Browser uploads.** The presigned link must name an address the browser reaches, but the seed task uploads from inside the network, so a setting for every container would not do (the first seed failed exactly so: `httpx.ConnectError` on `localhost:4566` inside the task). `infra/modules/ecs` gained `api_extra_environment`, plain variables for the API only, with `extra_environment`'s rule that no module setting may be replaced (`api_extra_environment_reaches_the_api_only`, `rejects_api_extra_environment_that_overrides_a_module_setting`); `local` sets `OBJECT_STORE_PUBLIC_ENDPOINT_URL=http://localhost:4566` there. In the run: the link's host is `http://localhost:4566`, the preflight answers `Access-Control-Allow-Origin: http://egyk4lut4xh5sr.cloudfront.localhost:4566` and `Access-Control-Allow-Methods: GET, PUT`, the PUT answers 200 with the same origin, and the seed's uploads went to `http://floci:4566/...` from inside.

**Per-Visitor address.** The catalogue's ranges (loopback and the rehearsal network) are in the API's `TRUSTED_PROXIES` (`10.0.0.0/16,127.0.0.0/8,172.29.0.0/16`). The API's peer for a sign-in through the distribution is Floci (`172.29.0.2`), yet the per-IP sign-in counter it created is `sign-in-failures:ip:127.0.0.1`, this machine; with an `X-Forwarded-For: 203.0.113.9` from the client it is `...ip:203.0.113.9` ([usable-studio.log](23-04-evidence/usable-studio.log)). Without the trusted ranges every Visitor would count as `172.29.0.2`.

**The seed as a one-off task; the Owner signs in.** `make rehearse-seed` (`rehearse.sh seed`, `--reset` through `REHEARSAL_SEED_ARGS`) runs the unchanged `seed.sh` on `local` with the wrapper's settings (`seed_runs_the_unchanged_seed_script_on_the_local_environment`, `seed_passes_reset_on`, `seed_fails_when_the_seed_fails`). On the fresh rehearsal it ran once and reported `The demo environment is seeded`; `owner@northwind.example` then signed in through the distribution (200 and the `studio_session` cookie) ([fresh-run.log](23-04-evidence/fresh-run.log)).

**An uploaded Document becomes Ready.** The Markdown file uploaded through the presigned link was confirmed and was `ready` with 2 Chunks 8 s later; the seed's four Documents (Markdown, DOCX, PPTX) were all `ready` too. The general worker took the jobs from the `https://floci:4566/...` queue Terraform named, read the files from the Documents bucket Terraform named (SSE-KMS with the data key), wrote Chunks to the database at Terraform's address and port, and holds its locks in the cache over TLS. The API sealed the seed's Provider Credential with the credentials key through Floci's KMS (`POST .../credentials` 201); the worker itself opens credential envelopes only for Runs, which 23-05 exercises.

**No drift after an apply, and the wrapper fails on drift.** `rehearse.sh up` plans again after the deploy (`plan -detailed-exitcode` at the deployed tag) and stops with the plan unless it shows no changes (`up_checks_that_a_second_plan_after_the_apply_shows_no_changes`, `up_fails_when_the_plan_after_the_apply_shows_changes`, `up_fails_when_the_plan_after_the_apply_fails`). 23-02's inputs removed the four drifts 23-01 found; the rehearsal found a fifth: Floci drops the tags the provider sends in `CreateFunction`, so a fresh apply left the SPA fallback function's tags to change. `infra/modules/cdn` gained `function_tags` (default true; `the_spa_fallback_function_is_tagged_by_default`, `function_tags_false_leaves_the_function_untagged`), and `local` sets it false and drops the provider's `default_tags` (every module tags its own resources, `ManagedBy` included). On a fresh rehearsal after a full teardown: 161 resources applied, smoke check passed, "The plan after the apply shows no changes." ([fresh-run.log](23-04-evidence/fresh-run.log)).

**Tests and coverage.** Module and environment behaviour is tested with `terraform test` (ecs 99 runs, cdn 33, storage 21, local 10), the wrapper with `rehearse.test.sh`; `make infra-check` passes ([infra-check.log](23-04-evidence/infra-check.log)). No backend or frontend code changed, so the 100% gate is unaffected.

**Glossary and ADRs.** No new domain term; no ADR decision changed.

## Gaps and best guesses

- **Deep links (not met; needs a human).** Tried on the running rehearsal: with `custom_error_responses = [{ 404 -> 200 /index.html }]` Floci answered `/widget/a/smoke-check` and `/api/nope` with the Studio's HTML (200, no Content-Security-Policy), and the smoke check failed; with `response_code = 404` the status stays 404 but the body and headers are still replaced, so the widget shell check fails the same way. Floci 2.5.0 has no setting that runs CloudFront Functions. `local` therefore adds no custom error response (`adds_no_custom_error_response`), and a deep link answers 404. Options for whoever decides: drop the criterion and list deep links among what the rehearsal does not prove (with the CloudFront Function); or accept a broken widget smoke check and API 404s in the rehearsal (not recommended); or wait for Floci to run functions (its issue 6695).
- **No real browser.** The browser's steps were done with curl (same requests, `Origin` header and preflight); the Studio UI itself was not clicked through. Human-eyes: open the address, sign in as the demo Owner, upload a file.
- **seed.sh prints only the first page of the seed task's log.** The seed task logs about 10,000 lines (telemetry spans among them), and `aws logs get-log-events` returns the first 10,000 events, so the closing report with the sign-in details is cut off; the demo accounts are the published ones (`backend/app/seed/content.py`, the README). The same limit applies on AWS: recorded for 22-09, script unchanged here.
- **The general worker runs close to its 3 GB:** 2.87 GB (page cache included) after ingesting the seed's Documents, without an OOM kill; a PDF was not tried (its models were left out of this image).
