// Records one screen recording per core user story (docs/demo.md) against the seeded compose stack.
//
//   make dev && make seed-reset          # a fresh demo Organisation
//   node scripts/demo-videos/record.cjs [out-dir] [story-slug ...]
//   scripts/demo-videos/encode.sh [out-dir]   # WebM -> docs/demo/*.mp4 and posters
//
// It drives the Studio the way the e2e suite does (same accessible names), adds a caption bar and
// outlines each control before clicking it, so a viewer can follow along. It changes the demo data
// (a new Organisation, an Agent, an invite, a spent Token Budget), so reseed before rerunning.
"use strict";

const fs = require("fs");
const path = require("path");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    const { createRequire } = require("module");
    return createRequire(path.join(__dirname, "../../frontend/package.json"))("@playwright/test");
  }
}
const { chromium } = loadPlaywright();

const ROOT = path.join(__dirname, "../..");
const STUDIO = process.env.E2E_BASE_URL || "http://localhost:5173";
const HOST = process.env.E2E_HOST_URL || "http://localhost:5175";
const MAILPIT = process.env.E2E_MAILPIT_URL || "http://localhost:8025";
const OUT = path.resolve(process.argv[2] || path.join(__dirname, "out"));
const ONLY = process.argv.slice(3);
const PACE = Number(process.env.PACE || 1);
const SIZE = { width: 1440, height: 900 };

const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const RUN = Date.now().toString(36);
const NEWCOMER = {
  name: "Ada Lovelace",
  email: `ada-${RUN}@acme.example`,
  password: "acme-support-demo-password",
  organisation: "Acme Outdoors",
};
const DOCS = ["northwind-staff-handbook.md", "northwind-returns-policy.md", "northwind-product-faq.docx", "northwind-spring-range.pptx"].map(
  (file) => path.join(ROOT, "seed/documents", file),
);

fs.mkdirSync(OUT, { recursive: true });

// ───────────────────────── overlay: caption bar ─────────────────────────

const OVERLAY = () => {
  const install = () => {
    if (document.getElementById("__cap")) return;
    const el = document.createElement("div");
    el.id = "__cap";
    el.setAttribute("aria-hidden", "true");
    el.style.cssText =
      "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:2147483647;max-width:min(88%,1100px);" +
      "background:rgba(15,23,42,.92);color:#fff;font:600 18px/1.4 system-ui,sans-serif;padding:10px 18px;" +
      "border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.35);pointer-events:none;text-align:center;";
    const t = sessionStorage.getItem("__cap") || "";
    el.textContent = t;
    el.style.display = t ? "block" : "none";
    document.documentElement.appendChild(el);
  };
  window.__setCap = (t) => {
    sessionStorage.setItem("__cap", t);
    install();
    const el = document.getElementById("__cap");
    el.textContent = t;
    el.style.display = t ? "block" : "none";
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
};

const wait = (page, ms) => page.waitForTimeout(ms * PACE);

async function cap(page, text, hold = 2600) {
  await page.evaluate((t) => window.__setCap && window.__setCap(t), text).catch(() => {});
  await wait(page, hold);
}

async function outline(locator, ms = 700) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  await locator
    .evaluate((el) => {
      el.dataset.demoOutline = el.style.outline;
      el.style.outline = "3px solid #f59e0b";
      el.style.outlineOffset = "2px";
    })
    .catch(() => {});
  await locator.page().waitForTimeout(ms * PACE);
  await locator.evaluate((el) => (el.style.outline = el.dataset.demoOutline || "")).catch(() => {});
}

async function click(locator, hold = 700) {
  await outline(locator, hold);
  await locator.click();
}

async function type(locator, text) {
  await locator.click();
  await locator.pressSequentially(text, { delay: 35 });
}

async function smooth(locator, block = "center") {
  await locator.evaluate((el, b) => el.scrollIntoView({ block: b, behavior: "smooth" }), block);
  await locator.page().waitForTimeout(700);
}

// ───────────────────────── navigation helpers ─────────────────────────

const sidebar = (p) => p.getByRole("navigation", { name: "Studio" });
const orgLink = (p, n) => sidebar(p).getByRole("list", { name: "Organisation sections", exact: true }).getByRole("link", { name: n, exact: true });
const projLink = (p, n) => sidebar(p).getByRole("list", { name: "Project sections", exact: true }).getByRole("link", { name: n, exact: true });
const agentTab = (p, n) => p.getByRole("navigation", { name: "Agent views", exact: true }).getByRole("link", { name: n, exact: true });
const settingsTab = (p, n) => p.getByRole("navigation", { name: "Organisation settings", exact: true }).getByRole("link", { name: n, exact: true });

async function signIn(page, member) {
  const response = await page.request.post(`${STUDIO}/api/auth/sign-in`, { data: { email: member.email, password: member.password } });
  if (!response.ok()) throw new Error(`sign-in answered ${response.status()}`);
}

async function openHandbook(page) {
  await page.goto(`${STUDIO}/`);
  await click(orgLink(page, "Projects"));
  await click(page.getByRole("link", { name: "Northwind Handbook" }));
  await projLink(page, "Documents").waitFor();
}

async function openAgent(page, name) {
  await click(projLink(page, "Agents"));
  await click(page.getByRole("table", { name: "Agents" }).getByRole("link", { name, exact: true }));
  await page.getByRole("heading", { level: 1, name }).waitFor();
}

async function openSettings(page, section) {
  const details = page.getByRole("complementary", { name: "Configuration" }).locator("details").filter({
    has: page.locator(`fieldset[aria-label="${section}"]`),
  });
  if (!(await details.evaluate((e) => e.open))) await click(details.locator("summary"));
}

async function ask(page, agent, question) {
  const box = page.getByLabel("Question", { exact: true });
  await type(box, question);
  await click(page.getByRole("button", { name: "Send" }));
  const answer = page.getByRole("list", { name: "Playground messages" }).getByRole("listitem", { name: agent }).last();
  await answer.getByText("Trace", { exact: true }).waitFor({ timeout: 45_000 });
  return answer;
}

async function draftSaved(page) {
  await page.getByRole("status", { name: "Draft status" }).getByText("All changes saved").waitFor({ timeout: 15_000 });
}

// ───────────────────────── the stories ─────────────────────────

const STORIES = [];
const story = (slug, title, fn) => STORIES.push({ slug, title, fn });
let agentPublicId = null;

story("01-get-started", "Sign up and create a Project", async (page) => {
  await page.goto(`${STUDIO}/`);
  await cap(page, "A team lead signs up: one form creates their account and their Organisation", 3000);
  await click(page.getByRole("link", { name: "Create an account" }));
  await type(page.getByLabel("Your name"), NEWCOMER.name);
  await type(page.getByLabel("Email"), NEWCOMER.email);
  await type(page.getByLabel("Password"), NEWCOMER.password);
  await type(page.getByLabel("Organisation name"), NEWCOMER.organisation);
  await click(page.getByRole("button", { name: "Create account" }));
  await page.getByRole("heading", { level: 1, name: "Projects" }).waitFor();
  await cap(page, "They're the Organisation's Owner. A Project holds the Documents its Agents answer from", 3200);
  await click(page.getByRole("button", { name: "New Project" }));
  const form = page.getByRole("form", { name: "New Project" });
  await type(form.getByLabel("Name"), "Customer Support");
  await type(form.getByLabel("Description"), "Policies and product facts for the support assistant");
  await click(form.getByRole("button", { name: "Create Project" }));
  await page.getByRole("heading", { level: 2, name: "Documents" }).waitFor();
  await cap(page, "The new Project opens on its Documents, ready for a Knowledge Base", 3000);
  await click(orgLink(page, "Settings"));
  await page.getByRole("heading", { name: "Organisation settings" }).waitFor();
  await cap(page, "Organisation settings: Credentials and Models for the LLM provider, Theme, Members and the Audit log", 3500);
  await click(settingsTab(page, "Credentials"));
  await cap(page, "Provider keys are envelope-encrypted; the demo model needs none", 3000);
});

story("02-knowledge-base", "Build a Knowledge Base", async (page) => {
  await signIn(page, NEWCOMER);
  await page.goto(`${STUDIO}/`);
  await click(page.getByRole("link", { name: "Customer Support" }));
  await page.getByRole("heading", { level: 2, name: "Documents" }).waitFor();
  await cap(page, "Upload Documents: drop files, or choose them. Markdown, DOCX, PPTX, HTML, text and PDF", 3000);
  await page.getByLabel("Upload", { exact: true }).setInputFiles(DOCS);
  await cap(page, "Each file is converted to Markdown, split into Chunks and embedded in the background", 2000);
  const table = page.getByRole("table", { name: "Documents" });
  for (const file of DOCS.map((f) => path.basename(f))) {
    await table.getByRole("row", { name: new RegExp(file.replace(/\./g, "\\.")) }).getByRole("cell", { name: "Ready" }).waitFor({ timeout: 180_000 });
  }
  await cap(page, "All four are Ready: Chunk counts per Document, and two Chunks flagged as possible instructions to an AI", 3800);
  await click(table.getByRole("link", { name: "northwind-returns-policy.md" }));
  await page.getByRole("region", { name: "Chunks" }).waitFor();
  await cap(page, "The Document viewer: the converted Markdown beside the Chunks an Agent can retrieve", 3200);
  const flagged = page
    .getByRole("region", { name: "Chunks" })
    .getByRole("listitem")
    .filter({ has: page.getByRole("note", { name: "Guardrail flag" }) })
    .first();
  await smooth(flagged);
  await outline(flagged, 1200);
  await cap(page, "A planted “note for AI assistants” was flagged at ingestion, the first defence against indirect prompt injection", 4200);
});

story("03-build-an-agent", "Create an Agent and test it in the Playground", async (page) => {
  await signIn(page, OWNER);
  await openHandbook(page);
  await click(projLink(page, "Agents"));
  await cap(page, "Northwind's Handbook Project already has Agents. An Editor adds one for returns questions", 2800);
  await click(page.getByRole("button", { name: "New Agent" }));
  const form = page.getByRole("form", { name: "New Agent" });
  await type(form.getByLabel("Name"), "Returns assistant");
  await click(form.getByRole("button", { name: "Create Agent" }));
  await page.getByRole("heading", { level: 1, name: "Returns assistant" }).waitFor({ timeout: 15_000 });
  await cap(page, "A new Agent is a Draft: the Playground on the left, its configuration on the right, autosaved", 3200);
  const prompt = page.getByRole("textbox", { name: "System prompt" });
  await prompt.click();
  await page.keyboard.press("ControlOrMeta+A");
  await prompt.pressSequentially("You help Northwind customers with returns and refunds. Be brief and cite the policy.", { delay: 20 });
  await openSettings(page, "Retrieval");
  const retrieval = page.getByRole("group", { name: "Retrieval" });
  await smooth(retrieval.getByText("Tag scoping"));
  await click(retrieval.getByRole("checkbox", { name: "Products" }));
  await cap(page, "Tag scoping keeps it to Product Documents; top-k, hybrid weighting, minimum score and Retrieval Mode are here too", 3800);
  await draftSaved(page);
  await smooth(page.getByLabel("Question", { exact: true }));
  const answer = await ask(page, "Returns assistant", "Can I return a jar of honey?");
  await cap(page, "Answers stream in with Citations: each Source chip links to the Chunk in the Document viewer", 3500);
  await click(answer.getByText("Trace", { exact: true }));
  await smooth(answer.getByRole("group", { name: "Trace" }), "start");
  await cap(page, "The Trace shows the model, tokens, cost, latency and every Chunk retrieved, given to the model or excluded", 4200);
});

story("04-publish-and-embed", "Publish an Agent and embed it on a website", async (page, { browser }) => {
  await signIn(page, OWNER);
  await openHandbook(page);
  await openAgent(page, "Returns assistant");
  await cap(page, "Visitors can't use a Draft. Publishing makes an immutable Version Live", 2800);
  await click(page.getByRole("banner").getByRole("button", { name: "Publish" }));
  const publish = page.getByRole("form", { name: "Publish" });
  await type(publish.getByLabel("Note"), "First release for the shop");
  await click(publish.getByRole("button", { name: "Publish" }));
  await publish.getByRole("status").getByText(/It is now Live\./).waitFor({ timeout: 15_000 });
  await cap(page, "v1 is Live, pinned to the Project Instructions it was published with", 2800);
  await click(page.getByRole("dialog").getByRole("button", { name: "Close" }));
  await click(agentTab(page, "Embed & limits"));
  const embed = page.getByRole("region", { name: "Embed Snippet" });
  await embed.locator("code").waitFor();
  agentPublicId = /data-agent="([^"]+)"/.exec(await embed.locator("code").innerText())[1];
  await outline(embed, 1200);
  await cap(page, "One script tag embeds the Agent on any site…", 2600);
  const origins = page.getByRole("region", { name: "Allowed Origins" });
  await smooth(origins);
  await type(origins.getByRole("textbox", { name: "Add an Allowed Origin" }), HOST);
  await origins.getByRole("textbox", { name: "Add an Allowed Origin" }).press("Enter");
  await click(origins.getByRole("button", { name: "Save Allowed Origins" }));
  await origins.getByText(/Saved\./).waitFor({ timeout: 15_000 });
  await cap(page, "…but only on the origins you allow (enforced by the browser with frame-ancestors)", 3200);
  await cap(page, "Rate limits, a daily Token Budget and the widget's text live on this tab too", 2600);

  // The Visitor's side: the host page pastes the snippet.
  await page.goto(`${HOST}/?agent=${agentPublicId}`);
  await cap(page, "On the shop's own site, a Visitor opens the chat", 2400);
  const widget = page.frameLocator('iframe[title="Chat"]');
  await click(widget.getByRole("button", { name: "Open chat" }));
  await type(widget.getByLabel("Message"), "How long do I have to return something?");
  await click(widget.getByRole("button", { name: "Send" }));
  const reply = widget.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "Returns assistant" }).last();
  const thumbs = reply.getByRole("group", { name: "Was this reply helpful?" });
  await thumbs.waitFor({ timeout: 45_000 });
  await cap(page, "The answer streams in with its Sources, and the Visitor can rate it", 2600);
  await click(thumbs.getByRole("button", { name: "Helpful", exact: true }));
  await cap(page, "That thumbs-up is recorded against v1, ready for analytics", 2600);
});

story("05-versions", "Iterate safely with Versions, Diffs and revert", async (page) => {
  await signIn(page, OWNER);
  await openHandbook(page);
  await openAgent(page, "HR helper");
  await click(agentTab(page, "Versions"));
  const timeline = page.getByRole("list", { name: "Live History" });
  await timeline.waitFor();
  await cap(page, "Live History: every publish and revert, newest first, with who did it and their note", 3500);
  await outline(timeline, 1200);
  await cap(page, "v2 (“shorter answers, without citations”) went Live, did worse, and was reverted to v1. Then v3 shipped", 4000);
  await page.mouse.wheel(0, 500);
  await wait(page, 1500);
  await cap(page, "Every Version is an immutable snapshot of the Agent's configuration, so any two can be compared", 3000);
  const actions = page.getByRole("button", { name: "Actions for the Live Version" });
  if (await actions.count()) {
    await smooth(actions);
    await click(actions);
    await cap(page, "Reverting is one click: the earlier Version goes Live again, without touching the Draft", 3200);
    await page.keyboard.press("Escape");
  }
  await click(projLink(page, "Instructions"));
  await wait(page, 1200);
  await cap(page, "Project Instructions are versioned too: shared rules every Agent in the Project follows", 3200);
  await page.mouse.wheel(0, 400);
  await wait(page, 1500);
});

story("06-conversations-analytics", "Review Conversations and compare Versions", async (page) => {
  await signIn(page, OWNER);
  await openHandbook(page);
  await click(projLink(page, "Conversations"));
  const list = page.getByRole("list", { name: "Conversations" });
  await list.getByRole("listitem").first().waitFor({ timeout: 15_000 });
  await cap(page, "Every Visitor and Playground Conversation, with its Agent, Version, feedback and rating", 3200);
  const filters = page.getByRole("group", { name: "Filter Conversations" });
  await click(filters.getByRole("radio", { name: "Visitors" }));
  await filters.getByLabel("Feedback").selectOption("Thumbs down");
  await outline(filters.getByLabel("Feedback"), 800);
  await cap(page, "Filter to the replies Visitors disliked…", 2200);
  await click(list.getByRole("listitem").first().getByRole("link").first());
  const messages = page.getByRole("list", { name: "Messages" });
  await messages.waitFor();
  await cap(page, "…and read the whole Conversation, each reply pinned to the Version that wrote it", 3000);
  const trace = messages.getByText("Trace", { exact: true }).last();
  await click(trace);
  await smooth(messages.getByRole("group", { name: "Trace" }).last(), "start");
  await cap(page, "The same Trace as the Playground: why the Agent answered as it did", 3200);

  await click(projLink(page, "Analytics"));
  await page.getByRole("combobox", { name: "Agent" }).selectOption({ label: "HR helper" });
  await cap(page, "Analytics: KPIs per Version — volume, tokens, cost, thumbs-up with a 95% interval, fallback and latency", 3600);
  for (const version of ["v1", "v2", "v3 (Live)"]) {
    await page.getByRole("combobox", { name: /^Version/ }).selectOption({ label: version });
    await cap(page, `HR helper ${version}`, 1800);
  }
  const compare = page.getByRole("table", { name: /compared with/ });
  if (await compare.count()) {
    await smooth(compare);
    await cap(page, "Compare two Versions side by side, with the configuration changes that explain the difference", 3800);
  }
});

story("07-agentic-retrieval", "Choose Automatic or Agentic retrieval", async (page) => {
  await signIn(page, OWNER);
  await openHandbook(page);
  await openAgent(page, "HR helper");
  await openSettings(page, "Retrieval");
  await smooth(page.getByRole("group", { name: "Retrieval" }).getByRole("radiogroup", { name: "Retrieval mode" }));
  await cap(page, "HR helper is Automatic: one search on the Visitor's exact words, then one model call. Cheap and predictable", 3600);
  await smooth(page.getByLabel("Question", { exact: true }));
  const hr = await ask(page, "HR helper", "How many days of annual leave do I get?");
  await click(hr.getByText("Trace", { exact: true }));
  await smooth(hr.getByRole("group", { name: "Trace" }).getByRole("table", { name: "Retrieved Chunks" }), "start");
  await cap(page, "Its Trace: one up-front search, one Retrieved Chunks table", 3000);

  await openAgent(page, "Product FAQ");
  await openSettings(page, "Retrieval");
  await smooth(page.getByRole("group", { name: "Retrieval" }).getByRole("radiogroup", { name: "Retrieval mode" }));
  await cap(page, "Product FAQ is Agentic: the model gets one read-only tool, Knowledge Search, and a Search limit", 3600);
  await smooth(page.getByLabel("Question", { exact: true }));
  const question = "Can I return a jar of honey?";
  const faq = await ask(page, "Product FAQ", question);
  await smooth(faq);
  await cap(page, "The model decided to search, and wrote its own query: “Searching: …”", 3200);
  await click(faq.getByText("Trace", { exact: true }));
  await smooth(faq.getByRole("group", { name: "Trace" }).getByRole("list", { name: "Searches" }).getByRole("heading").first(), "start");
  await cap(page, "Its Trace lists each Search with the Chunks it found. Multi-part questions and follow-ups get their own searches", 4200);

  await page.goto(`${HOST}/demo/`);
  await cap(page, "On the shop page, Visitors see a short status while it searches, never the model's query", 2600);
  const widget = page.frameLocator('iframe[title="Chat"]');
  await click(widget.getByRole("button", { name: "Open chat" }));
  await type(widget.getByLabel("Message"), question);
  await click(widget.getByRole("button", { name: "Send" }));
  await cap(page, "“Searching the knowledge base…”, then the answer with its Sources", 4000);
});

story("08-guardrails", "See the Guardrails stop prompt injection", async (page) => {
  await page.goto(`${HOST}/demo/attacks.html`);
  await cap(page, "The attack panel sends real attacks to a demo Agent and shows which Guardrail layer acted", 3200);
  for (const [button, note] of [
    ["Instruction override", "“Ignore your instructions…” is blocked by the input Guardrail, a local classifier"],
    ["Prompt extraction", "Asking for the system prompt: blocked at the input"],
    ["Encoded attack (base64)", "A base64 attack slips past the classifier; the model starts to leak and the Canary token replaces the reply"],
    ["Benign control", "An ordinary question goes straight through and is answered"],
  ]) {
    await click(page.getByRole("button", { name: button, exact: true }));
    const result = page.getByRole("region", { name: button });
    await page.getByRole("status").getByText(`${button}: done.`).waitFor({ timeout: 45_000 });
    await smooth(result);
    await cap(page, note, 3800);
  }
  await signIn(page, OWNER);
  await openHandbook(page);
  await click(projLink(page, "Analytics"));
  const guardrails = page.getByText("Guardrail block rate").first();
  await smooth(guardrails);
  await outline(guardrails, 1000);
  await cap(page, "Blocks, Canary leaks and flagged Chunks are counted in Analytics, and the Attack suite runs in CI", 3600);
});

story("09-team-and-cost", "Manage the team, spending and audit trail", async (page, { browser }) => {
  await signIn(page, OWNER);
  await page.goto(`${STUDIO}/`);
  await click(orgLink(page, "Settings"));
  await click(settingsTab(page, "Members"));
  await cap(page, "Owners manage Members: Owners administer, Editors build Agents", 2800);
  await click(page.getByRole("button", { name: "Invite someone" }));
  const form = page.getByRole("form", { name: "Invite someone" });
  const invitee = `grace-${RUN}@northwind.example`;
  await type(form.getByLabel("Email", { exact: true }), invitee);
  await form.getByLabel("Role").selectOption("Editor");
  await click(form.getByRole("button", { name: "Invite" }));
  await page.getByRole("region", { name: "New invite" }).waitFor();
  await cap(page, "The invite is emailed, and its link stays on the page to copy", 3000);
  await page.goto(MAILPIT);
  await cap(page, "Here it is in the stack's test mailbox (Mailpit)", 1200);
  await click(page.getByText(invitee).first());
  await wait(page, 2500);
  await page.goto(`${STUDIO}/`);
  await click(orgLink(page, "Settings"));
  await click(settingsTab(page, "General"));
  await outline(page.getByRole("button", { name: "Require two-factor authentication" }), 1000);
  await cap(page, "General settings: Owners can require two-factor authentication and set how long Message text is kept", 3400);

  await page.goto(`${HOST}/demo/budget.html`);
  await cap(page, "Each Agent can have a daily Token Budget. This demo page spends one in a click", 2800);
  await click(page.getByRole("button", { name: "Use up today's Token Budget" }));
  await page.getByRole("status").getByText(/Token Budget is spent/).waitFor({ timeout: 15_000 });
  const widget = page.frameLocator('iframe[title="Chat"]');
  await type(widget.getByLabel("Message"), "Do you sell honey?");
  await click(widget.getByRole("button", { name: "Send" }));
  await widget.getByRole("alert").waitFor({ timeout: 15_000 });
  await cap(page, "Visitors get the Agent's own “unavailable” text instead of a surprise bill", 3200);

  await page.goto(`${STUDIO}/`);
  await click(orgLink(page, "Cost"));
  await page.getByRole("heading", { level: 1, name: "Organisation cost" }).waitFor();
  await cap(page, "Organisation cost: what each Project spent, Visitors and Playground apart, at the prices frozen per reply", 3600);
  await click(page.getByRole("radiogroup", { name: "Break down by" }).getByRole("radio", { name: "Agent" }));
  await cap(page, "…or broken down by Agent", 2400);
  await click(orgLink(page, "Settings"));
  await click(settingsTab(page, "Audit"));
  await page.getByRole("table", { name: "Audit Events" }).getByRole("row").nth(1).waitFor({ timeout: 15_000 });
  await cap(page, "The Audit log: every change, by whom, with before and after", 3000);
  await page.getByRole("combobox", { name: "Action" }).selectOption("agent.published");
  await cap(page, "Filter by action, actor or date", 2800);
});

// ───────────────────────── runner ─────────────────────────

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const { slug, title, fn } of STORIES) {
    if (ONLY.length && !ONLY.includes(slug)) continue;
    const dir = path.join(OUT, slug);
    fs.rmSync(dir, { recursive: true, force: true });
    const context = await browser.newContext({ viewport: SIZE, recordVideo: { dir, size: SIZE }, colorScheme: "light" });
    await context.addInitScript(OVERLAY);
    const page = await context.newPage();
    page.setDefaultTimeout(20_000);
    const started = Date.now();
    let error = null;
    try {
      await fn(page, { browser, context });
      await cap(page, "", 800);
    } catch (e) {
      error = e.message.split("\n")[0];
      await page.screenshot({ path: path.join(OUT, `${slug}-failure.png`) }).catch(() => {});
    }
    const video = page.video();
    await context.close();
    const file = path.join(OUT, `${slug}.webm`);
    await video.saveAs(file);
    fs.rmSync(dir, { recursive: true, force: true });
    const seconds = ((Date.now() - started) / 1000).toFixed(0);
    console.log(`${error ? "FAIL" : "ok  "} ${slug} (${seconds}s)${error ? `: ${error}` : ""}`);
    results.push({ slug, title, file, error });
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "stories.json"), JSON.stringify(results, null, 2));
  process.exitCode = results.some((r) => r.error) ? 1 : 0;
})();
