import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper, oldHelper, STALE_DRAFT } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeEvaluationApi } from "../test/evaluation";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { citingSuggestion, cleanDiff, fakeSuggestionsApi, retrievalSuggestion, STALE_NOTICE } from "../test/suggestions";

const organisationId = adaSession.organisations[0]?.id ?? "";
const publishedHelper: typeof hrHelper = { ...hrHelper, live_version: { id: "a1e00000-0000-4000-8000-000000000001", number: 1 } };
const evaluationPage = (agentId: string) => `/organisations/${organisationId}/projects/${hrProject.id}/agents/${agentId}/evaluation`;
const DETAIL = "Suggestion of 2026-11-16 09:00 UTC";
const prompt = citingSuggestion.changes[0] as (typeof citingSuggestion.changes)[number];

/** A Draft that has changed the system prompt some other way, so it clashes. */
const clashing = cleanDiff(citingSuggestion, {
  changes: [{ ...(cleanDiff(citingSuggestion).changes[0] as ReturnType<typeof cleanDiff>["changes"][number]), draft_value: "Be brief.", state: "clash" }],
  clashes: 1,
});

/** Their Draft, saved after the review was read. */
const theirs: typeof hrHelper = { ...publishedHelper, draft_revision: 5, draft_updated_at: "2026-11-16T09:30:00Z" };

function setUp(options: Parameters<typeof fakeSuggestionsApi>[0] = {}, agents = [publishedHelper]) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents });
  fakeEvaluationApi();
  return fakeSuggestionsApi(options);
}

async function openDetail(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("radio", { name: "Suggestions" }, { timeout: 5000 }));
  const tab = await screen.findByRole("region", { name: "Suggestions" });
  return { tab, detail: await within(tab).findByRole("region", { name: DETAIL }) };
}

async function openReview(user: ReturnType<typeof userEvent.setup>) {
  const { tab, detail } = await openDetail(user);
  await user.click(within(detail).getByRole("button", { name: "Apply to Draft" }));
  const dialog = await screen.findByRole("dialog", { name: "Apply to Draft" });
  return { tab, detail, dialog, changes: await within(dialog).findByRole("list", { name: "Changes to the Draft" }) };
}

test("an Editor reviews a Suggestion against the Draft and applies it whole, never Publishing", async () => {
  const user = userEvent.setup();
  const api = setUp({ suggestions: [[citingSuggestion]] });
  renderStudio(evaluationPage(publishedHelper.id));

  const { tab, detail, dialog, changes } = await openReview(user);

  expect(dialog).toHaveTextContent("It doesn't Publish: evaluate the Draft again before Publishing it.");
  const row = within(changes).getByRole("listitem");
  expect(within(row).getByRole("heading", { level: 4, name: "System prompt" })).toBeInTheDocument();
  expect(row).toHaveTextContent("Will be applied");
  const diff = within(row).getByRole("table", { name: "The system prompt: your Draft and the Suggestion" });
  expect(within(diff).getByText("Always cite the passage you used.").closest("tr")).toHaveTextContent("Added");
  await user.click(within(dialog).getByRole("button", { name: "Apply to Draft" }));

  // Applied on the revision reviewed.
  await waitFor(() => {
    expect(screen.queryByRole("dialog", { name: "Apply to Draft" })).not.toBeInTheDocument();
  });
  expect(api.applies).toEqual([3]);
  expect(await screen.findByText("Applied to the Draft. Evaluate it again before Publishing.")).toBeInTheDocument();
  expect(await within(detail).findByText("Applied by Ada Lovelace, 2026-11-16 10:00 UTC.")).toBeInTheDocument();
  const runs = within(tab).getByRole("list", { name: "Suggestion runs" });
  expect(await within(runs).findByText("Applied by Ada Lovelace, 2026-11-16 10:00 UTC")).toBeInTheDocument();
});

test("a Draft that already has every suggested value says so once applied", async () => {
  const user = userEvent.setup();
  const applied = cleanDiff(citingSuggestion);
  setUp({
    suggestions: [[citingSuggestion]],
    diffs: [{ ...applied, changes: applied.changes.map((change) => ({ ...change, draft_value: change.suggested_value, state: "applied" as const })) }],
    apply: () =>
      HttpResponse.json({ agent: publishedHelper, suggestion: citingSuggestion, paths: [], stale_notice: null }),
  });
  renderStudio(evaluationPage(publishedHelper.id));
  const { dialog, changes } = await openReview(user);

  expect(within(changes).getByRole("listitem")).toHaveTextContent("Already in the Draft");
  await user.click(within(dialog).getByRole("button", { name: "Apply to Draft" }));

  expect(await screen.findByText("The Draft already had every suggested value.")).toBeInTheDocument();
});

test("clashes are listed and applying waits until the Editor resolves them in the Draft", async () => {
  const user = userEvent.setup();
  const api = setUp({ suggestions: [[citingSuggestion]], diffs: [clashing] });
  renderStudio(evaluationPage(publishedHelper.id));

  const { dialog, changes } = await openReview(user);

  expect(dialog).toHaveTextContent("1 setting clashes with your Draft: it has changed them some other way.");
  const row = within(changes).getByRole("listitem");
  expect(row).toHaveTextContent("Clash");
  expect(row).toHaveTextContent("Your Draft has changed the system prompt some other way. In the Draft, set it back to Answer from the handbook. or to the suggested value, then apply.");
  expect(within(dialog).getByRole("button", { name: "Apply to Draft" })).toBeDisabled();
  await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog", { name: "Apply to Draft" })).not.toBeInTheDocument();
  expect(api.applies).toEqual([]);
});

test("a clash found on applying lists each setting with its three values, and the review reads the Draft again", async () => {
  const user = userEvent.setup();
  const clash = {
    detail: "Your Draft has also changed settings this Suggestion changes. Resolve each clash in the Draft, then apply it again.",
    conflict: "suggestion_clash",
    latest: null,
    clashes: [{ path: prompt.path, base_value: prompt.base_value, draft_value: "Be brief.", suggested_value: prompt.suggested_value }],
  };
  setUp({
    suggestions: [[citingSuggestion]],
    diffs: [cleanDiff(citingSuggestion), clashing],
    apply: () => HttpResponse.json(clash, { status: 409 }),
  });
  renderStudio(evaluationPage(publishedHelper.id));
  const { dialog, changes } = await openReview(user);

  await user.click(within(dialog).getByRole("button", { name: "Apply to Draft" }));

  const alert = await within(dialog).findByRole("alert");
  expect(alert).toHaveTextContent(clash.detail);
  const listed = within(alert).getByRole("list", { name: "Clashes" });
  expect(listed).toHaveTextContent(
    "System prompt: was Answer from the handbook., your Draft has Be brief., the Suggestion has Answer from the handbook. Always cite the passage you used..",
  );
  expect(await within(changes).findByText("Clash")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Apply to Draft" })).toBeDisabled();
});

test("a colleague's save in between shows the shared conflict prompt: save mine over theirs applies on their Draft", async () => {
  const user = userEvent.setup();
  const api = setUp({
    suggestions: [[citingSuggestion]],
    apply: (baseRevision) =>
      baseRevision === 3 ? HttpResponse.json({ detail: STALE_DRAFT, conflict: "stale_draft", latest: theirs, clashes: [] }, { status: 409 }) : undefined,
  });
  renderStudio(evaluationPage(publishedHelper.id));
  const { dialog } = await openReview(user);

  await user.click(within(dialog).getByRole("button", { name: "Apply to Draft" }));

  const conflict = await within(dialog).findByRole("alert");
  expect(conflict).toHaveTextContent("Someone else saved this Draft while you were editing");
  await user.click(within(conflict).getByRole("button", { name: "Save mine over theirs" }));
  await waitFor(() => {
    expect(api.applies).toEqual([3, 5]);
  });
  expect(await screen.findByText("Applied to the Draft. Evaluate it again before Publishing.")).toBeInTheDocument();
});

test("loading their changes reads the review again against their Draft", async () => {
  const user = userEvent.setup();
  const api = setUp({
    suggestions: [[citingSuggestion]],
    diffs: [cleanDiff(citingSuggestion), clashing],
    apply: () => HttpResponse.json({ detail: STALE_DRAFT, conflict: "stale_draft", latest: theirs, clashes: [] }, { status: 409 }),
  });
  renderStudio(evaluationPage(publishedHelper.id));
  const { dialog, changes } = await openReview(user);
  await user.click(within(dialog).getByRole("button", { name: "Apply to Draft" }));

  await user.click(await within(dialog).findByRole("button", { name: "Load their changes" }));

  expect(await within(changes).findByText("Clash")).toBeInTheDocument();
  expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
  expect(api.applies).toEqual([3]);
});

test("a Suggestion from an earlier Live Version is marked stale and still applies, saying its check was against the old Live", async () => {
  const user = userEvent.setup();
  const stale = { ...citingSuggestion, stale: true };
  setUp({ suggestions: [[stale]] });
  renderStudio(evaluationPage(publishedHelper.id));
  const { tab, detail } = await openDetail(user);

  expect(within(within(tab).getByRole("list", { name: "Suggestion runs" })).getByText("Stale")).toBeInTheDocument();
  expect(detail).toHaveTextContent(
    "Made from Version 1, which is no longer Live: its check was against the old Live Version. You can still apply it.",
  );
  await user.click(within(detail).getByRole("button", { name: "Apply to Draft" }));
  const dialog = await screen.findByRole("dialog", { name: "Apply to Draft" });

  expect(await within(dialog).findByText(STALE_NOTICE)).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Apply to Draft" })).toBeEnabled();
});

test("an apply refused for another reason says why", async () => {
  const user = userEvent.setup();
  setUp({ suggestions: [[citingSuggestion]], apply: () => HttpResponse.json({ detail: "This Agent is archived. An Owner can restore it." }, { status: 409 }) });
  renderStudio(evaluationPage(publishedHelper.id));
  const { dialog } = await openReview(user);

  await user.click(within(dialog).getByRole("button", { name: "Apply to Draft" }));

  expect(await within(dialog).findByText("This Agent is archived. An Owner can restore it.")).toBeInTheDocument();
});

test("a review that can't be read says so and can't be applied", async () => {
  const user = userEvent.setup();
  setUp({ suggestions: [[citingSuggestion]] });
  const { server } = await import("../test/server");
  const { http } = await import("msw");
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/suggestions/:suggestionId/diff", () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );
  renderStudio(evaluationPage(publishedHelper.id));
  const { detail } = await openDetail(user);
  await user.click(within(detail).getByRole("button", { name: "Apply to Draft" }));
  const dialog = await screen.findByRole("dialog", { name: "Apply to Draft" });

  expect(await within(dialog).findByText("The Draft could not be read. Not found")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Apply to Draft" })).toBeDisabled();
});

test("an Editor deletes a Suggestion after confirming; a refused delete says why", async () => {
  const user = userEvent.setup();
  const api = setUp({ suggestions: [[citingSuggestion], [retrievalSuggestion]] });
  renderStudio(evaluationPage(publishedHelper.id));
  const { tab, detail } = await openDetail(user);

  await user.click(within(detail).getByRole("button", { name: "Delete Suggestion" }));
  let confirm = await screen.findByRole("alertdialog", { name: "Delete this Suggestion?" });
  expect(confirm).toHaveTextContent("The Draft and the replies it points at are kept.");
  await user.click(within(confirm).getByRole("button", { name: "Cancel" }));
  expect(api.deletes).toEqual([]);
  await user.click(within(detail).getByRole("button", { name: "Delete Suggestion" }));
  confirm = await screen.findByRole("alertdialog", { name: "Delete this Suggestion?" });
  await user.click(within(confirm).getByRole("button", { name: "Delete Suggestion" }));

  expect(await screen.findByText("Suggestion deleted.")).toBeInTheDocument();
  expect(api.deletes).toEqual([citingSuggestion.id]);
  await waitFor(() => {
    expect(within(within(tab).getByRole("list", { name: "Suggestion runs" })).getAllByRole("listitem")).toHaveLength(1);
  });
});

test("a refused delete says why and keeps the Suggestion", async () => {
  const user = userEvent.setup();
  setUp({ suggestions: [[citingSuggestion]], deleteStatus: 409 });
  renderStudio(evaluationPage(publishedHelper.id));
  const { detail } = await openDetail(user);

  await user.click(within(detail).getByRole("button", { name: "Delete Suggestion" }));
  const confirm = await screen.findByRole("alertdialog", { name: "Delete this Suggestion?" });
  await user.click(within(confirm).getByRole("button", { name: "Delete Suggestion" }));

  expect(await within(confirm).findByText("This Agent is archived. An Owner can restore it.")).toBeInTheDocument();
  await user.click(within(confirm).getByRole("button", { name: "Cancel" }));
  expect(screen.getByRole("region", { name: DETAIL })).toBeInTheDocument();
});

test("an archived Agent's Suggestions can't be applied or deleted, and a former Member's apply reads as such", async () => {
  const user = userEvent.setup();
  const applied = { ...citingSuggestion, applied_at: "2026-11-15T08:00:00Z", applied_by: null };
  setUp({ suggestions: [[applied]] }, [oldHelper]);
  renderStudio(evaluationPage(oldHelper.id));
  const { tab, detail } = await openDetail(user);

  expect(within(detail).queryByRole("button", { name: "Apply to Draft" })).not.toBeInTheDocument();
  expect(within(detail).queryByRole("button", { name: "Delete Suggestion" })).not.toBeInTheDocument();
  expect(detail).toHaveTextContent("Applied by a former Member, 2026-11-15 08:00 UTC.");
  expect(within(tab).getByRole("list", { name: "Suggestion runs" })).toHaveTextContent("Applied by a former Member, 2026-11-15 08:00 UTC");
});
