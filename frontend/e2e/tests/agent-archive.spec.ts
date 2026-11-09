import { expect, test } from "../fixtures";
import { agentAction } from "../fixtures/agent";
import { openSection } from "../fixtures/navigation";

test.describe("Agent Archive and delete", () => {
  test("an Owner archives an Agent, restores it, then deletes it permanently after typing its name", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Agent archive");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await openSection(page, "Project sections", "Agents");
    for (const name of ["Old helper", "HR helper"]) {
      await page.getByRole("form", { name: "New Agent" }).getByLabel("Name").fill(name);
      await page.getByRole("form", { name: "New Agent" }).getByRole("button", { name: "Create Agent" }).click();
      await expect(page.getByRole("heading", { level: 2, name })).toBeVisible({ timeout: 15_000 });
      await openSection(page, "Project sections", "Agents");
    }

    // Archive: the Agent leaves the list, its page turns read only and the Playground goes.
    await page.getByRole("list", { name: "Agents" }).getByRole("link", { name: "Old helper" }).click();
    await expect(page.getByRole("heading", { name: "Playground" })).toBeVisible({ timeout: 15_000 });
    await agentAction(page, "Archive");
    await page.getByRole("alertdialog", { name: "Archive Old helper?" }).getByRole("button", { name: "Yes, archive Old helper" }).click();
    const notice = page.getByRole("status", { name: "Archived" });
    await expect(notice).toContainText("This Agent is archived.");
    await expect(page.getByRole("heading", { name: "Playground" })).toHaveCount(0);
    await expect(page.getByRole("status", { name: "Draft status" })).toHaveText("Read only while archived.");
    await expect(page.getByLabel("Chunks per answer (top-k)")).toBeDisabled();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await openSection(page, "Project sections", "Agents");
    await expect(page.getByRole("list", { name: "Agents" }).getByRole("link")).toHaveText(["HR helper"]);
    await page.getByRole("button", { name: "Show archived Agents" }).click();
    await expect(page.getByRole("list", { name: "Archived Agents" }).getByRole("link")).toHaveText(["Old helper"]);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Restore brings it back with its Playground.
    await page.getByRole("list", { name: "Archived Agents" }).getByRole("link", { name: "Old helper" }).click();
    await notice.getByRole("button", { name: "Restore Old helper" }).click();
    await expect(page.getByRole("heading", { name: "Playground" })).toBeVisible();
    await expect(notice).toHaveCount(0);

    // Permanent deletion needs it archived again and its name typed exactly.
    await agentAction(page, "Archive");
    await page.getByRole("button", { name: "Yes, archive Old helper" }).click();
    await expect(notice).toBeVisible();
    await agentAction(page, "Delete permanently");
    const confirm = page.getByRole("alertdialog", { name: "Delete Old helper permanently" });
    const button = confirm.getByRole("button", { name: "Delete Old helper permanently" });
    await confirm.getByLabel("Type Old helper to confirm").fill("old helper");
    await expect(button).toBeDisabled();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await confirm.getByLabel("Type Old helper to confirm").fill("Old helper");
    await button.click();

    await expect(page.getByText("Old helper was deleted permanently.")).toBeVisible();
    await expect(page.getByRole("list", { name: "Agents" }).getByRole("link")).toHaveText(["HR helper"]);
    await page.getByRole("button", { name: "Show archived Agents" }).click();
    await expect(page.getByText("No archived Agents.")).toBeVisible();

    // Every step is in the Audit tab.
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Audit");
    const audit = page.getByRole("table", { name: "Audit Events" });
    await expect(audit.getByRole("cell", { name: "agent.archived" })).toHaveCount(2);
    await expect(audit.getByRole("cell", { name: "agent.restored" })).toHaveCount(1);
    await expect(audit.getByRole("cell", { name: "agent.deleted" })).toHaveCount(1);
  });
});
