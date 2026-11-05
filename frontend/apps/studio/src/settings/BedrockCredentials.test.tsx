import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { bedrockKeys, bedrockRole, bedrockSetup, fakeCredentialsApi, marketingOpenAi } from "../test/credentials";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const credentialsPath = `/organisations/${organisationId}/settings/credentials`;

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

async function bedrockForm() {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  const form = within(await screen.findByRole("region", { name: "Add a credential" }));
  await userEvent.selectOptions(form.getByLabelText("Provider"), "Amazon Bedrock");
  return form;
}

test("Bedrock is offered alongside the API-key providers", async () => {
  fakeCredentialsApi({ credentials: [] });
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  const form = within(await screen.findByRole("region", { name: "Add a credential" }));

  expect(within(form.getByLabelText("Provider")).getAllByRole("option").map((o) => o.textContent)).toEqual([
    "Anthropic",
    "OpenAI",
    "Amazon Bedrock",
    "Voyage AI",
  ]);
});

test("the role option is recommended and chosen by default, with what to paste into AWS", async () => {
  const api = fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();

  const how = form.getByRole("radiogroup", { name: "How should we connect to your AWS account?" });
  expect(within(how).getByLabelText("IAM role (recommended)")).toBeChecked();
  expect(within(how).getByLabelText("Access keys")).not.toBeChecked();
  expect(form.getByText(/no secret is stored/)).toBeInTheDocument();
  expect(form.queryByLabelText("API key")).not.toBeInTheDocument();

  const setup = within(await form.findByRole("region", { name: "Set up the role in AWS" }));
  expect(setup.getByLabelText("Your external ID")).toHaveValue(bedrockSetup.external_id);
  expect(setup.getByLabelText("Our AWS principal")).toHaveValue(bedrockSetup.platform_principal);
  expect(setup.getByLabelText("Trust policy")).toHaveValue(bedrockSetup.trust_policy);
  expect(setup.getByLabelText("Permissions policy")).toHaveValue(bedrockSetup.permissions_policy);
  expect(api.setupRequests).toBe(1);
});

test("an Owner copies the trust policy and the permissions policy", async () => {
  fakeCredentialsApi({ credentials: [] });
  const copied: string[] = [];
  stubClipboard((text) => {
    copied.push(text);
    return Promise.resolve();
  });
  const form = await bedrockForm();
  const setup = within(await form.findByRole("region", { name: "Set up the role in AWS" }));

  await userEvent.click(setup.getByRole("button", { name: "Copy trust policy" }));
  expect(await setup.findByText("Trust policy copied.")).toBeInTheDocument();
  await userEvent.click(setup.getByRole("button", { name: "Copy permissions policy" }));
  expect(await setup.findByText("Permissions policy copied.")).toBeInTheDocument();
  await userEvent.click(setup.getByRole("button", { name: "Copy external ID" }));
  expect(await setup.findByText("External ID copied.")).toBeInTheDocument();

  expect(copied).toEqual([bedrockSetup.trust_policy, bedrockSetup.permissions_policy, bedrockSetup.external_id]);
});

test("a copy that fails says to copy by hand", async () => {
  fakeCredentialsApi({ credentials: [] });
  stubClipboard(() => Promise.reject(new Error("denied")));
  const form = await bedrockForm();
  const setup = within(await form.findByRole("region", { name: "Set up the role in AWS" }));

  await userEvent.click(setup.getByRole("button", { name: "Copy trust policy" }));

  expect(await setup.findByText("Couldn't copy. Select the text and copy it yourself.")).toBeInTheDocument();
});

test("the setup helper says when it can't be loaded", async () => {
  fakeCredentialsApi({ credentials: [] });
  server.use(http.get("*/api/organisations/:organisationId/bedrock-setup", () => new HttpResponse(null, { status: 500 })));
  const form = await bedrockForm();

  expect(await form.findByText("The AWS setup details could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("an Owner adds a Bedrock credential with a role", async () => {
  const api = fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();
  await userEvent.type(form.getByLabelText("Name"), "Bedrock prod");
  await userEvent.type(form.getByLabelText("Role ARN"), "arn:aws:iam::111122223333:role/StudioBedrockAccess");
  await userEvent.clear(form.getByLabelText("AWS region"));
  await userEvent.type(form.getByLabelText("AWS region"), "eu-west-2");
  await userEvent.click(form.getByLabelText("Reranking"));

  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByText("Bedrock prod was checked and saved.")).toBeInTheDocument();
  expect(api.added).toEqual([
    {
      name: "Bedrock prod",
      auth_kind: "aws_role",
      role_arn: "arn:aws:iam::111122223333:role/StudioBedrockAccess",
      region: "eu-west-2",
      capabilities: ["chat", "embeddings"],
    },
  ]);
  const row = within((await screen.findByText("arn:aws:iam::111122223333:role/StudioBedrockAccess")).closest("tr") as HTMLElement);
  expect(row.getByText("Amazon Bedrock · eu-west-2")).toBeInTheDocument();
  expect(form.getByLabelText("Name")).toHaveValue("");
  expect(form.getByLabelText("Role ARN")).toHaveValue("");
});

test("the region starts at us-east-1", async () => {
  fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();

  expect(form.getByLabelText("AWS region")).toHaveValue("us-east-1");
});

test("an Owner adds a Bedrock credential with access keys", async () => {
  const api = fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();
  await userEvent.click(form.getByLabelText("Access keys"));

  expect(form.getByText(/Prefer the IAM role/)).toBeInTheDocument();
  expect(form.queryByRole("region", { name: "Set up the role in AWS" })).not.toBeInTheDocument();
  expect(form.queryByLabelText("Role ARN")).not.toBeInTheDocument();
  expect(form.getByLabelText("Secret access key")).toHaveAttribute("type", "password");
  await userEvent.type(form.getByLabelText("Name"), "Bedrock sandbox");
  await userEvent.type(form.getByLabelText("Access key ID"), "AKIAIOSFODNN7EXAMPLE");
  await userEvent.type(form.getByLabelText("Secret access key"), "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY");
  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByText("Bedrock sandbox was checked and saved.")).toBeInTheDocument();
  expect(api.added).toEqual([
    {
      name: "Bedrock sandbox",
      auth_kind: "aws_access_keys",
      access_key_id: "AKIAIOSFODNN7EXAMPLE",
      secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
      region: "us-east-1",
      capabilities: ["chat", "embeddings", "rerank"],
    },
  ]);
  expect(await screen.findByLabelText("Key ending MPLE")).toBeInTheDocument();
  expect(form.getByLabelText("Access key ID")).toHaveValue("");
  expect(form.getByLabelText("Secret access key")).toHaveValue("");
});

test.each([
  [
    "role_not_assumable",
    "We couldn't assume this role. Check the role ARN, and that the role's trust policy is exactly the one shown, with your external ID.",
  ],
  [
    "missing_model_access",
    "The role works, but it can't use the model. Enable model access in the Bedrock console for this region, and check the role's permissions policy.",
  ],
  ["wrong_region", "Bedrock, or this model, isn't available in that region. Choose the region where you enabled model access."],
])("a failed role check shows a clear reason (%s)", async (reason, message) => {
  fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();
  await userEvent.type(form.getByLabelText("Name"), "Broken");
  await userEvent.type(form.getByLabelText("Role ARN"), `arn:aws:iam::111122223333:role/fail-${reason}`);

  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(`The check failed. ${message}`);
  expect(form.getByLabelText("Role ARN")).toHaveValue(`arn:aws:iam::111122223333:role/fail-${reason}`);
});

test("rejected access keys say so", async () => {
  fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();
  await userEvent.click(form.getByLabelText("Access keys"));
  await userEvent.type(form.getByLabelText("Name"), "Broken keys");
  await userEvent.type(form.getByLabelText("Access key ID"), "AKIAIOSFODNN7EXAMPLE");
  await userEvent.type(form.getByLabelText("Secret access key"), "fail-invalid_key-secret");

  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The check failed. AWS rejected this access key. Check the access key ID and secret access key were copied in full.",
  );
});

test("the API's refusal of a malformed role ARN is shown as it is", async () => {
  fakeCredentialsApi({ credentials: [] });
  server.use(
    http.post("*/api/organisations/:organisationId/credentials/bedrock", () =>
      HttpResponse.json({ detail: "A secret access key is 16 to 128 characters, with no spaces or line breaks." }, { status: 422 }),
    ),
  );
  const form = await bedrockForm();
  await userEvent.type(form.getByLabelText("Name"), "Bad");
  await userEvent.type(form.getByLabelText("Role ARN"), "arn:aws:iam::111122223333:role/x");

  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("A secret access key is 16 to 128 characters");
});

test("switching back to an API-key provider brings back the API key field", async () => {
  fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();

  await userEvent.selectOptions(form.getByLabelText("Provider"), "Anthropic");

  expect(form.getByLabelText("API key")).toBeInTheDocument();
  expect(form.queryByRole("radiogroup")).not.toBeInTheDocument();
});

test("Bedrock credentials show their role or key, region and Bedrock-specific status, and can't be rotated", async () => {
  fakeCredentialsApi({ credentials: [bedrockRole, bedrockKeys, marketingOpenAi] });
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  const table = within(await screen.findByRole("table", { name: "Provider Credentials" }));
  const [, roleRow, keysRow] = table.getAllByRole("row").map((row) => within(row));

  expect(roleRow?.getByText("Amazon Bedrock · eu-west-2")).toBeInTheDocument();
  expect(roleRow?.getByLabelText("IAM role arn:aws:iam::111122223333:role/StudioBedrockAccess")).toHaveTextContent("IAM role");
  expect(roleRow?.getByText(/Check failed: We couldn't assume this role/)).toBeInTheDocument();
  expect(keysRow?.getByLabelText("Key ending MPLE")).toBeInTheDocument();
  expect(keysRow?.getByText("Amazon Bedrock · us-east-1")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Rotate key: Bedrock prod" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Rotate key: Bedrock sandbox" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Rotate key: Marketing OpenAI" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Check now: Bedrock prod" })).toBeInTheDocument();
});

test("re-checking a Bedrock credential that fails shows the Bedrock reason", async () => {
  fakeCredentialsApi({ credentials: [{ ...bedrockKeys }], recheck: "wrong_region" });
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);

  await userEvent.click(await screen.findByRole("button", { name: "Check now: Bedrock sandbox" }));

  expect(await screen.findByText(/Check failed: Bedrock, or this model, isn't available in that region/)).toBeInTheDocument();
});

test("an Owner who looked at access keys can go back to the role", async () => {
  fakeCredentialsApi({ credentials: [] });
  const form = await bedrockForm();
  await userEvent.click(form.getByLabelText("Access keys"));
  expect(form.queryByLabelText("Role ARN")).not.toBeInTheDocument();

  await userEvent.click(form.getByLabelText("IAM role (recommended)"));

  expect(form.getByLabelText("IAM role (recommended)")).toBeChecked();
  expect(form.getByLabelText("Role ARN")).toBeInTheDocument();
  expect(await form.findByRole("region", { name: "Set up the role in AWS" })).toBeInTheDocument();
  expect(form.queryByLabelText("Secret access key")).not.toBeInTheDocument();
});
