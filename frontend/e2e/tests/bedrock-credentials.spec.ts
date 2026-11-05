import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";

// The compose stack checks Bedrock credentials with the fake verifier: a role passes unless its
// name starts `fake-fail-<reason>`, and access keys pass unless the secret does. No AWS account
// is used; these ARNs and keys are made up (the access key is AWS's documentation example).
const ROLE_ARN = "arn:aws:iam::111122223333:role/StudioBedrockAccess";
const SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY";

async function openCredentials(page: Page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
  await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Credentials" }).click();
  await expect(page.getByRole("heading", { name: "Provider Credentials" })).toBeVisible();
}

test.describe("Bedrock credentials", () => {
  test("an Owner connects Bedrock with a role, guided by the trust policy to paste, or with access keys", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await openCredentials(page);
    const form = page.getByRole("region", { name: "Add a credential" });
    await form.getByLabel("Provider").selectOption("Amazon Bedrock");

    // The role is recommended and chosen; the Studio shows what to paste into AWS.
    await expect(form.getByLabel("IAM role (recommended)")).toBeChecked();
    const setup = form.getByRole("region", { name: "Set up the role in AWS" });
    const externalId = await setup.getByLabel("Your external ID").inputValue();
    expect(externalId).toMatch(/^[A-Za-z0-9_-]{32,}$/);
    const trust = JSON.parse(await setup.getByLabel("Trust policy").inputValue()) as {
      Statement: { Action: string; Condition: { StringEquals: Record<string, string> } }[];
    };
    expect(trust.Statement[0]?.Action).toBe("sts:AssumeRole");
    expect(trust.Statement[0]?.Condition.StringEquals["sts:ExternalId"]).toBe(externalId);
    await expect(setup.getByLabel("Permissions policy")).toHaveValue(/bedrock:InvokeModel/);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // A role the platform can't assume is refused with the reason.
    await form.getByLabel("Name").fill("Bedrock prod");
    await form.getByLabel("Role ARN").fill("arn:aws:iam::111122223333:role/fake-fail-role_not_assumable");
    await form.getByLabel("AWS region").fill("eu-west-2");
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByRole("alert")).toContainText("We couldn't assume this role.");

    // A role that works is saved, with no secret.
    await form.getByLabel("Role ARN").fill(ROLE_ARN);
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Bedrock prod was checked and saved.")).toBeVisible();
    const table = page.getByRole("table", { name: "Provider Credentials" });
    const roleRow = table.getByRole("row", { name: /Bedrock prod/ });
    await expect(roleRow).toContainText("Amazon Bedrock · eu-west-2");
    await expect(roleRow).toContainText(ROLE_ARN);
    await expect(roleRow).toContainText("Working");
    await page.getByRole("button", { name: "Check now: Bedrock prod" }).click();
    await expect(page.getByText("Bedrock prod passed its check.")).toBeVisible();

    // The external ID stays the same for the Organisation.
    await page.reload();
    await form.getByLabel("Provider").selectOption("Amazon Bedrock");
    await expect(setup.getByLabel("Your external ID")).toHaveValue(externalId);

    // Access keys are the fallback; a region without the model is refused with the reason.
    await form.getByLabel("Access keys").check();
    await expect(form.getByText(/Prefer the IAM role/)).toBeVisible();
    await form.getByLabel("Name").fill("Bedrock sandbox");
    await form.getByLabel("Access key ID").fill("AKIAIOSFODNN7EXAMPLE");
    await form.getByLabel("Secret access key").fill("fake-fail-wrong_region-e2e-000000");
    await form.getByLabel("AWS region").fill("us-east-1");
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByRole("alert")).toContainText("isn't available in that region");
    await form.getByLabel("Secret access key").fill(SECRET_ACCESS_KEY);
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Bedrock sandbox was checked and saved.")).toBeVisible();
    const keysRow = table.getByRole("row", { name: /Bedrock sandbox/ });
    await expect(keysRow).toContainText("••••MPLE");
    await expect(page.getByRole("button", { name: "Rotate key: Bedrock sandbox" })).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // No API answer carries the secret access key.
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const id = me.organisations[0]?.id ?? "";
    for (const path of [`/api/organisations/${id}/credentials`, `/api/organisations/${id}/audit-events?size=100`]) {
      expect(await (await page.request.get(path)).text()).not.toContain(SECRET_ACCESS_KEY.slice(0, 20));
    }
  });
});
