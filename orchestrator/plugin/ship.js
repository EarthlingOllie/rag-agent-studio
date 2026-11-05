export const meta = { name: 'ship-ticket', description: 'Build the standard ship-one-ticket chain and run dispatch.js' }
// Builds the standard "ship one ticket" chain spec from compact args and runs dispatch.js.
// args: { now, scratch, humans?, t: { id, spec, ticket, name, slug, dependsOn[], notes[]?, infra? } }
const S = args.scratch
const t = args.t
const branch = `ticket/${t.ticket}-${t.slug}`
const ev = `docs/tickets/${t.spec}/${t.ticket}-evidence/`
const tag = `${t.spec}/${t.ticket} (${t.name})`
const limits = t.infra
  ? "limits: merge only into candidate, never main; NEVER terraform apply or create real cloud resources — fmt/validate/tflint/checkov/terraform test with mock providers; list real-account gaps in evidence README; never stall on a human question — record best guess"
  : "limits: merge only into candidate, never main; no real cloud resources/credentials, no real email or paid external APIs (use spec-allowed local/test doubles); gaps listed in evidence README; never stall on a human question — record best guess in evidence README"
const context = [
  `YOUR TICKET IS ${tag}; branch ${branch}; evidence ${ev}`,
  `orientation note (ticket paths, deps): ${S}/orientation.md; frontier helper ${S}/bin/frontier.py`,
  "evidence examples: any docs/tickets/*/*-evidence/README.md already on candidate",
  "convention: claim = first commit on branch sets ticket '**Status:** in-progress' and is pushed; done = ticket '**Status:** done' committed in the same PR",
  `build in your own git worktree under ${S}; check origin for an existing branch/PR for ${t.ticket} and resume it`,
  "other tickets build in parallel — keep changes scoped to your ticket",
  "GitHub ops only via mcp__github__* tools (ToolSearch); owner EarthlingOllie repo rag-agent-studio",
  limits,
  ...(t.notes || []),
]
const ret = { shape: "line1: PR URL + merged sha; then one line per currently-unblocked ticket: <spec>/<ticket-id> title", maxLines: 18 }
const dispatch = {
  id: t.id,
  title: `Ship ticket ${t.ticket} ${t.slug.split('-').slice(0, 2).join(' ')}`,
  topology: "chain",
  task: `Deliver ticket ${tag} end to end: built, tested, evidenced, merged into candidate, marked done.`,
  context,
  roles: {},
  params: { stages: [
    { title: `Build and evidence ${t.ticket}`, topology: "generator-evaluator",
      task: `On branch ${branch}, claim ticket ${tag}, implement every acceptance criterion${t.infra ? " verifiable offline" : ""}, make all test/lint/typecheck${t.infra ? "" : "/e2e"} checks pass, write ${ev} with a README mapping each criterion to evidence, set ticket Status to done, commit and push.`,
      roles: {
        generator: { skill: "mattpocock-skills:tdd", instructions: "Read the ticket and parent spec first. Claim commit+push before building. Do not open PRs or merge." },
        evaluator: { skill: "code-review", instructions: `Fresh checkout of the pushed branch. Run make test/lint${t.infra ? " plus terraform fmt -check/validate/test" : " and any e2e the ticket names"}. Verify each acceptance criterion of ${t.ticket} against code and evidence${t.infra ? "; real-account-only criteria pass if offline parts are done and the gap is documented" : ""}; numbered specific feedback on any gap. Change nothing.` },
      },
      params: { pass_criteria: `every acceptance criterion of ${t.ticket} met and evidenced in ${ev} with README mapping; all checks pass from clean checkout; ticket status done; branch pushed`, max_iterations: 3 },
      returns: { shape: "branch and head sha; PASS line; one line per criterion not fully met in-sandbox", maxLines: 5 } },
    { title: `PR and merge ${t.ticket}`, topology: "single",
      task: `Update branch ${branch} from latest origin/candidate (merge, resolve conflicts, rerun tests, push), create (or reuse) a PR into base 'candidate' titled 'Ticket ${t.ticket}: ${t.name}' with body summarising changes, linking ${ev} and listing in-sandbox gaps, ending with '🤖 Generated with [Claude Code](https://claude.com/claude-code)'; ${args.localMerge ? "run full local checks, then merge (merge commit) on local green — CI is down and the user authorised local-evidence merges" : "wait for CI green, merge"}, then list every ticket whose deps are all Status: done on candidate and which is not itself done or in-progress.`,
      roles: { worker: { instructions: args.localMerge
        ? "Only merge into candidate. GitHub Actions is down repo-wide and the USER AUTHORISED merging on local test results: after updating from candidate, run the full make test, make lint, typecheck and e2e (and terraform fmt/validate/test for infra) from the updated branch; if all green, put the local results in the PR body, push, and merge with merge_method 'merge' (not squash) without waiting for CI. If local checks fail, fix on the branch; if you cannot make them green return blocked with the failure. If candidate moved before merge, update and re-run local checks."
        : "Only merge into candidate. If CI fails, fix on the branch and push; if you cannot make it green return blocked with the failure. If candidate moved during CI, update again and re-wait." } },
      returns: ret },
  ] },
  returns: ret,
  dependsOn: t.dependsOn || [],
}
return await workflow({ scriptPath: `${S}/plugin/dispatch.js` }, { now: args.now, scratch: S, dispatch, humans: args.humans || [] })
