# Tickets

Tickets break a slice spec (`docs/specs/NN-*-spec.md`) into small units of work. Each ticket is sized for one pull request into `candidate` and can be merged on its own once its dependencies are done.

## Layout

```
docs/tickets/
├── README.md                          # this file: format and conventions
└── <spec>/                            # one folder per spec, named after the spec file without "-spec.md"
    ├── README.md                      # index: dependency graph and spec-to-ticket traceability (not a ticket)
    ├── <ticket>.md                    # one file per ticket
    └── <ticket>-evidence/             # created by the ticket's PR: proof the ticket is done
```

`<ticket>` is the ticket's file name without `.md`. It always starts with the ticket id, for example `S01-T03-auth-core`. Its evidence folder is `S01-T03-auth-core-evidence/`.

## Ticket format

Every ticket starts with YAML front matter:

```yaml
---
id: S01-T03                # S<spec number>-T<ticket number>; unique across all specs; never reused
title: Authentication core API
status: todo               # todo | claimed | done
depends_on: [S01-T02]      # ids of tickets that must be `done` before this one can be claimed; [] if none
spec: docs/specs/01-skeleton-auth-tenancy-spec.md
---
```

Optional front matter, set while a ticket is claimed: `claimed_by` (session or person), `branch`, `pr` (URL).

The body has these sections, in this order:

1. **Goal**: one or two sentences.
2. **Spec coverage**: the spec's user stories (`US n`) and Implementation/Testing Decisions this ticket delivers.
3. **Scope**: what is built. **Out of scope** names what is left to other tickets.
4. **Acceptance criteria**: checkboxes. Each ticket ends with the same *Done rule* block (below).
5. **Test plan**: the tests to write, named by seam (see `docs/specs/README.md`).

### Done rule

`docs/plan.md` §7 says a slice merges only with green CI, 100% coverage, the glossary and ADRs updated, and a short demo note in the PR. Every ticket applies that rule to its own PR, so each ticket's acceptance criteria end with:

- [ ] Every CI workflow that exists on `candidate` is green on the PR.
- [ ] Line and branch coverage stay at 100% in `backend/` and `frontend/` (ADR-0008).
- [ ] New domain terms are in `GLOSSARY.md`. Any decision that changes or adds to an ADR has a new or superseding ADR.
- [ ] The PR description has a short demo note, and the evidence folder exists.

The slice as a whole is done when every ticket in its folder is `done` and the plan's "Done when" line for the slice is shown by the final ticket's evidence.

## Status lifecycle: claim and done

The status in the ticket file on `candidate` is the source of truth.

**Claimable.** A ticket can be claimed when its `status` is `todo` and every id in `depends_on` has `status: done` on `origin/candidate`.

**Claim.**
1. `git fetch origin` and read the ticket on `origin/candidate`. Check that no open PR into `candidate` changes the ticket's file. If one does, the ticket is already claimed.
2. Create a work branch from `origin/candidate`.
3. Make the first commit on that branch change only the ticket's front matter: set `status: claimed` and add `claimed_by` and `branch`. Use the message `claim(<id>): <title>`.
4. Push the branch and open a **draft** PR into `candidate` straight away. Put its URL in `pr`. The open draft PR is the visible claim.

If two claims race, the PR opened first keeps the ticket and the other is closed. A claim with no commits on its branch for 7 days can be taken over. The new claimant says so in their claim commit message.

**Done.**
1. Do the work on the same branch, test-first where practical.
2. Add the evidence folder `docs/tickets/<spec>/<ticket>-evidence/` with at least a `README.md` that has:
   - a checklist mirroring the acceptance criteria, each item linked to its proof;
   - the commands run and their outcome (for example, the `make test` coverage summary);
   - links to the green CI runs;
   - screenshots, Mailpit captures or Playwright traces where the ticket has UI or email behaviour.
3. In the last commit, set `status: done` in the ticket, and tick its acceptance criteria.
4. Mark the PR ready for review, put the demo note in its description, and merge it into `candidate` once CI is green. Merging is what makes the ticket done for everyone else.

**Abandon.** To give a ticket up, set `status: todo`, remove `claimed_by`, `branch` and `pr`, and close the draft PR (or merge only that front-matter change).

## Rules for writing tickets

- One PR per ticket. Split a ticket that would not fit one reviewable PR.
- `depends_on` must keep the graph acyclic. A ticket may depend only on tickets with a lower number in the same spec, or on tickets of earlier specs.
- Every user story and decision in the spec maps to at least one ticket. The spec folder's `README.md` holds the traceability table.
- Never renumber or reuse an id. Tickets that are no longer needed are kept, with an explanation in their body.
