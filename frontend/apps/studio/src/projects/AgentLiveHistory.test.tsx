import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";

import type { Schemas } from "@studio/api-client";

import { fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

type Entry = Schemas["LiveHistoryEntryOut"];

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = (agentId: string) =>
  `/organisations/${organisationId}/projects/${hrProject.id}/agents/${agentId}/versions`;

const version = (number: number) => ({ id: `a1e00000-0000-4000-8000-${String(number).padStart(12, "0")}`, number });
const ada = { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a01", name: "Ada Lovelace" };
const grace = { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a02", name: "Grace Hopper" };

/** A Live History entry; `from` is null for a first publish. */
function entry(from: number | null, to: number, action = "publish", actor = ada, minute = 0): Entry {
  return {
    from_version: from === null ? null : version(from),
    to_version: version(to),
    action,
    actor,
    occurred_at: `2026-11-06T10:${String(minute).padStart(2, "0")}:00Z`,
    bulk_operation_id: null,
  };
}

/** Published v1, v2 and v3 in turn, newest first. */
const threePublishes = [entry(2, 3, "publish", ada, 3), entry(1, 2, "publish", grace, 2), entry(null, 1, "publish", ada, 1)];

function liveOn(number: number, agent = hrHelper) {
  return { ...agent, live_version: version(number) };
}

function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  return fakeAgentsApi({ currentInstructions: { id: "1a5e0000-0000-4000-8000-000000000002", number: 2 }, ...options });
}

async function timeline() {
  return screen.findByRole("list", { name: "Live History" }, { timeout: 5000 });
}

/** Chooses Revert in the Live Version's ⋯ menu. */
async function revertTo(version: string) {
  await userEvent.click(await screen.findByRole("button", { name: "Actions for the Live Version" }));
  await userEvent.click(screen.getByRole("menuitem", { name: `Revert to ${version}` }));
}

function rows(list: HTMLElement) {
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.textContent);
}

test("the Live History timeline lists every change of the Live Version, newest first, with who and when", async () => {
  const agent = liveOn(4);
  setUp({
    agents: [agent],
    liveHistory: {
      [agent.id]: [
        entry(3, 4, "bulk_publish", grace, 6),
        entry(4, 3, "bulk_revert", grace, 5),
        entry(3, 4, "publish", ada, 4),
        entry(2, 3, "revert", grace, 3),
        entry(2, 3, "publish", ada, 2),
        entry(1, 2, "publish", grace, 1),
        entry(null, 1, "publish", ada, 0),
      ],
    },
  });
  renderStudio(agentPage(agent.id));

  expect(rows(await timeline())).toEqual([
    "Bulk published v3 → v4Grace Hopper · 2026-11-06 10:06 UTC",
    "Bulk reverted v4 → v3Grace Hopper · 2026-11-06 10:05 UTC",
    "Published v3 → v4Ada Lovelace · 2026-11-06 10:04 UTC",
    "Reverted v2 → v3Grace Hopper · 2026-11-06 10:03 UTC",
    "Published v2 → v3Ada Lovelace · 2026-11-06 10:02 UTC",
    "Published v1 → v2Grace Hopper · 2026-11-06 10:01 UTC",
    "Published v1Ada Lovelace · 2026-11-06 10:00 UTC",
  ]);
  expect(screen.getByRole("heading", { name: "Live History" })).toBeInTheDocument();
});

test("an Agent that has never been Live has an empty timeline and nothing to revert", async () => {
  setUp({ agents: [hrHelper] });
  renderStudio(agentPage(hrHelper.id));

  expect(
    await screen.findByText("Nothing has been Live yet. Publish the Draft to make v1 Live.", {}, { timeout: 5000 }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Revert|Actions for the Live Version/ })).not.toBeInTheDocument();
});

test("the Editor is told when there's nothing to revert to", async () => {
  const agent = liveOn(1);
  setUp({ agents: [agent], liveHistory: { [agent.id]: [entry(null, 1)] } });
  renderStudio(agentPage(agent.id));

  await timeline();
  expect(screen.getByText("There's no earlier Live Version to revert to: v1 was the first.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Revert|Actions for the Live Version/ })).not.toBeInTheDocument();
});

test("reverting asks for confirmation, then makes the earlier Version Live and adds it to the timeline", async () => {
  const agent = liveOn(3);
  const { requests } = setUp({ agents: [agent], liveHistory: { [agent.id]: threePublishes } });
  renderStudio(agentPage(agent.id));
  await timeline();

  await revertTo("v2");
  const confirm = screen.getByRole("dialog", { name: "Revert to v2?" });
  expect(confirm).toHaveTextContent("Visitors are served v2 with the Instructions it pins at once. The Draft isn't changed.");
  await userEvent.click(within(confirm).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog", { name: "Revert to v2?" })).not.toBeInTheDocument();
  expect(requests.filter((r) => r.route === "revert")).toEqual([]);

  await revertTo("v2");
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v2" }));

  expect(await screen.findByText("Reverted to v2 with Instructions v2. It is now Live.")).toBeInTheDocument();
  expect(await screen.findByLabelText("Version 2")).toBeInTheDocument();
  expect(rows(await timeline())[0]).toBe("Reverted v3 → v2Ada Lovelace · 2026-11-06 12:00 UTC");
  expect(requests.filter((r) => r.route === "revert")).toEqual([{ route: "revert" }]);
});

test("reverting again follows the Live History further back instead of toggling", async () => {
  const agent = liveOn(3);
  setUp({ agents: [agent], liveHistory: { [agent.id]: threePublishes }, currentInstructions: null });
  renderStudio(agentPage(agent.id));
  await timeline();

  await revertTo("v2");
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v2" }));
  await vi.waitFor(async () => {
    expect(rows(await timeline())[0]).toMatch(/^Reverted v3 → v2/);
  });
  await revertTo("v1");
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v1" }));

  expect(await screen.findByText("Reverted to v1 without Project Instructions. It is now Live.")).toBeInTheDocument();
  expect(await screen.findByLabelText("Version 1")).toBeInTheDocument();
  expect(await screen.findByText("There's no earlier Live Version to revert to: v1 was the first.")).toBeInTheDocument();
});

test("a Version published and then reverted is skipped", async () => {
  const agent = liveOn(3);
  setUp({
    agents: [agent],
    liveHistory: {
      [agent.id]: [entry(1, 3, "publish", ada, 4), entry(2, 1, "revert", ada, 3), entry(1, 2, "publish", ada, 2), entry(null, 1)],
    },
  });
  renderStudio(agentPage(agent.id));
  await timeline();

  await userEvent.click(screen.getByRole("button", { name: "Actions for the Live Version" }));
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Revert to v1"]);
});

test("publishing adds the move to the timeline", async () => {
  setUp({ agents: [hrHelper] });
  renderStudio(agentPage(hrHelper.id));
  await userEvent.click(await within(await screen.findByRole("banner")).findByRole("button", { name: "Publish" }, { timeout: 5000 }));
  const form = await screen.findByRole("form", { name: "Publish" });

  await userEvent.type(within(form).getByLabelText("Note"), "First release");
  await userEvent.click(within(form).getByRole("button", { name: "Publish" }));

  expect(rows(await timeline())).toEqual(["Published v1Ada Lovelace · 2026-11-06 11:00 UTC"]);
});

test.each([
  [409, "This Agent is archived. An Owner can restore it.", "This Agent is archived. An Owner can restore it."],
  [500, undefined, "Something went wrong. Try again."],
])("a refused revert (%i) says why and leaves the Live Version", async (status, detail, message) => {
  const agent = liveOn(3);
  setUp({
    agents: [agent],
    liveHistory: { [agent.id]: threePublishes },
    revert: () => HttpResponse.json({ detail: detail ?? [] }, { status }),
  });
  renderStudio(agentPage(agent.id));
  await timeline();

  await revertTo("v2");
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v2" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByLabelText("Version 3")).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "Revert to v2?" })).not.toBeInTheDocument();
});

test("an archived Agent shows its timeline but can't be reverted", async () => {
  const agent = liveOn(3, oldHelper);
  setUp({ agents: [agent], liveHistory: { [agent.id]: threePublishes } });
  renderStudio(agentPage(agent.id));

  expect(rows(await timeline())).toHaveLength(3);
  expect(screen.queryByRole("button", { name: /Revert|Actions for the Live Version/ })).not.toBeInTheDocument();
});

test("the timeline says when the Live History can't be loaded", async () => {
  setUp({
    agents: [liveOn(1)],
    liveHistoryResponse: () => HttpResponse.json({ detail: "Something broke" }, { status: 500 }),
  });
  renderStudio(agentPage(hrHelper.id));

  expect(
    await screen.findByText("The Live History could not be loaded. Try again shortly.", {}, { timeout: 5000 }),
  ).toBeInTheDocument();
});
