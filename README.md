# RAG Agent Studio

A studio where Organisations build Agents grounded in a Knowledge Base, inside isolated Projects, and embed them on their own sites. The vocabulary is in [GLOSSARY.md](GLOSSARY.md), the decisions in [docs/adr](docs/adr), the build plan in [docs/plan.md](docs/plan.md) and the specs in [docs/specs](docs/specs).

## Run it locally

```sh
make dev     # the whole stack in docker compose
make seed    # the Demo Organisation, its Documents, Agents and four weeks of history; prints the sign-in details
```

`make seed` is idempotent: running it again adds only what is missing. `make seed-reset` erases the Demo Organisation (only that one) and builds it again. [docs/development.md](docs/development.md) has the addresses, the test suites and everything else for working on the code.

## Demo in AWS

The demo environment is applied on demand and destroyed afterwards. Once [the bootstrap](docs/infra-bootstrap.md) is in place, everything runs from GitHub Actions ([docs/deploy-demo.md](docs/deploy-demo.md) has the details and the expected cost):

1. **Deploy:** Actions, **deploy**, Run workflow. It applies Terraform at an image tag, runs the migrations, rolls the services, uploads the Studio, widget and demo pages, and smoke checks the CloudFront URL it prints.
2. **Seed:** Actions, **seed**, Run workflow. It runs the same seed as `make seed`, as a one-off ECS task, and prints its output: the URL and the demo Owner's and Editor's sign-in details. Running it again is idempotent; tick `reset` to erase and rebuild the Demo Organisation, like `make seed-reset`. From a laptop with AWS credentials: `TF_STATE_BUCKET=<state bucket> AWS_REGION=eu-west-2 scripts/deploy/seed.sh [--reset]`.
3. **Destroy:** Actions, **destroy**, Run workflow, and type `destroy demo`. Nothing keeps costing money except the bootstrap's state bucket and key.

## Licence

[MIT](LICENSE). The demo content in [seed](seed) is synthetic ([seed/LICENCE.md](seed/LICENCE.md)).
