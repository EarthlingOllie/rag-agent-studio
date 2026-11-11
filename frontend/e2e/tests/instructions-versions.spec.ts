import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

test.describe("Project Instructions Versions", () => {
  test("an Owner publishes the Instructions twice with notes, browses the history and reverts, all audited", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("button", { name: "New Project" }).click();
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Versioned HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await openSection(page, "Project sections", "Instructions");
    await expect(page.getByText("Not published yet. Publish the Draft to make v1, the Current Version.")).toBeVisible({
      timeout: 15_000,
    });

    const publishForm = page.getByRole("form", { name: "Publish Instructions" });
    await page.getByRole("button", { name: "Markdown" }).click();
    const source = page.getByRole("textbox", { name: "Project Instructions (Markdown)" });
    for (const [markdown, note, version] of [
      ["Be kind.", "First rules", "v1"],
      ["Be curt.", "Shorter answers", "v2"],
    ] as const) {
      await source.fill(markdown);
      await publishForm.getByRole("textbox", { name: "Note" }).fill(note);
      await publishForm.getByRole("button", { name: "Publish Instructions" }).click();
      // Publishing offers the rollout in a Dialog; this Project has no Agents to roll out to.
      const rollout = page.getByRole("dialog", { name: `Roll out Instructions ${version}` });
      await expect(rollout).toContainText("This Project has no Agents yet.", { timeout: 15_000 });
      await rollout.getByRole("button", { name: "Not now" }).click();
      await expect(publishForm.getByRole("status")).toHaveText(`Published ${version}`, { timeout: 15_000 });
    }

    const history = page.getByRole("list", { name: "Instructions Versions" });
    await expect(page.getByText("Current Version: v2.")).toBeVisible();
    await expect(history.getByRole("listitem")).toHaveCount(2);
    await expect(history.getByRole("listitem", { name: "v2" })).toContainText("Shorter answers");
    await expect(history.getByRole("listitem", { name: "v2" }).getByText("Current")).toBeVisible();
    // The Draft compares with the Current Version by default, in the design system's Diff.
    await expect(page.getByRole("region", { name: "Compare" }).getByText("No differences: v2 and the Draft are the same.")).toBeVisible();
    await history.getByRole("listitem", { name: "v1" }).getByText("Show the Instructions").click();
    await expect(history.getByRole("listitem", { name: "v1" }).getByText("Be kind.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await page.getByRole("button", { name: "Revert to v1" }).click();
    await page.getByRole("alertdialog", { name: "Revert to v1?" }).getByRole("button", { name: "Yes, revert to v1" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Reverted to v1" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Current Version: v1.")).toBeVisible();
    await expect(history.getByRole("listitem", { name: "v1" }).getByText("Current")).toBeVisible();
    // The Draft is untouched by the revert.
    await expect(source).toHaveValue("Be curt.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The API agrees, and every publish and the revert are in the Audit log.
    const versionsUrl = `${page.url().replace(/^https?:\/\/[^/]+/, "/api")}/versions`;
    const listed = (await (await page.request.get(versionsUrl)).json()) as {
      current_version_id: string;
      versions: { id: string; number: number }[];
    };
    expect(listed.versions.map((version) => version.number)).toEqual([2, 1]);
    expect(listed.current_version_id).toBe(listed.versions[1]?.id);
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const actions = async (action: string) => {
      const audit = await page.request.get(`/api/organisations/${me.organisations[0]?.id ?? ""}/audit-events`, { params: { action } });
      return ((await audit.json()) as { items: { after: { current_version: { number: number } } }[] }).items.map(
        (item) => item.after.current_version.number,
      );
    };
    expect(await actions("project.instructions_published")).toEqual([2, 1]);
    expect(await actions("project.instructions_reverted")).toEqual([1]);
  });
});
