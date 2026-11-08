// The demo host: stand-ins for an Organisation's website, served by `docker compose` on their own
// origins so the widget is embedded cross-origin for real. No dependencies: plain Node.
//
// On PORT (5175, the shop origin the seed puts in the demo Agents' Allowed Origins):
// - `/demo/`: Northwind's fictional shop with the Product FAQ as a bubble; `/demo/inline.html`,
//   the same Agent in the page (the inline layout); `/demo/budget.html`, the Low-budget helper
//   and a button that spends its Token Budget. These are the static files in ./demo, the same
//   ones the deploy uploads to the static bucket under /demo/ in AWS (ticket 10-03).
// - `/?agent=agt_…`: pastes the Embed Snippet for any Agent, loading `embed.js` from WIDGET_URL
//   (the Studio's origin). `&launcher=inline` puts the widget in the page's #chat container and
//   `&launcher=bubble` asks for the bubble; without it the Theme's Launcher applies.
// On BLOCKED_PORT (5176, an origin no Agent allows), `/` is a page that tries to embed the
// Product FAQ and is refused by the browser. It is local-only: in AWS every page under /demo/ is
// on the Studio's own origin.
// Both proxy `/api/demo/` to API_URL, as CloudFront sends `/api/*` to the API in AWS, so the
// static pages can ask which Agents to embed.
import { readFileSync, readdirSync } from "node:fs";
import { createServer } from "node:http";

const port = Number(process.env.PORT ?? 5175);
const blockedPort = process.env.BLOCKED_PORT ? Number(process.env.BLOCKED_PORT) : undefined;
const widgetUrl = (process.env.WIDGET_URL ?? "http://localhost:5173").replace(/\/$/, "");
const apiUrl = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const here = new URL(".", import.meta.url);
const demoPages = new Map(
  readdirSync(new URL("demo/", here))
    .filter((name) => name.endsWith(".html"))
    .map((name) => [name, readFileSync(new URL(`demo/${name}`, here))]),
);
const blockedPage = readFileSync(new URL("blocked.html", here));

function escape(text) {
  return text.replace(/[&<>"']/g, (c) => `&#${String(c.charCodeAt(0))};`);
}

function page(agent, launcher) {
  const layout =
    launcher === "inline" ? ' data-launcher="inline" data-target="#chat"' : launcher === "bubble" ? ' data-launcher="bubble"' : "";
  const snippet = agent
    ? `<script src="${escape(widgetUrl)}/embed.js" data-agent="${escape(agent)}"${layout} async></script>`
    : '<p>Add <code>?agent=</code> and an Agent\'s public ID to the address to embed it, or see the <a href="/demo/">demo shop</a>.</p>';
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Northwind Traders</title>
<style>body{font:16px/1.5 system-ui,sans-serif;margin:0 auto;max-width:720px;padding:24px;color:#1e293b}</style>
</head>
<body>
<header><h1>Northwind Traders</h1></header>
<main>
<p>This is a demo host page on its own origin. The Agent's Embed Snippet shows the chat.</p>
<section id="chat" aria-label="Help"></section>
${snippet}
</main>
</body>
</html>
`;
}

const HTML = { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache" };

async function proxy(request, response, url) {
  try {
    const upstream = await fetch(`${apiUrl}${url.pathname}`, { method: request.method, headers: { Accept: "application/json" } });
    response
      .writeHead(upstream.status, { "Content-Type": upstream.headers.get("content-type") ?? "application/json" })
      .end(Buffer.from(await upstream.arrayBuffer()));
  } catch {
    response.writeHead(502, { "Content-Type": "application/json" }).end(JSON.stringify({ detail: "The API isn't reachable." }));
  }
}

function serve(handle) {
  return (request, response) => {
    const url = new URL(request.url ?? "/", "http://host");
    if (url.pathname === "/health") {
      response.writeHead(200, { "Content-Type": "text/plain" }).end("ok");
      return;
    }
    if (url.pathname.startsWith("/api/demo/")) {
      void proxy(request, response, url);
      return;
    }
    if (!handle(url, response)) response.writeHead(404, { "Content-Type": "text/plain" }).end("Not found");
  };
}

function shop(url, response) {
  if (url.pathname === "/") {
    const agent = url.searchParams.get("agent") ?? "";
    response.writeHead(200, HTML).end(page(/^[A-Za-z0-9_-]{1,64}$/.test(agent) ? agent : "", url.searchParams.get("launcher")));
    return true;
  }
  if (url.pathname === "/demo") {
    response.writeHead(301, { Location: "/demo/" }).end();
    return true;
  }
  const name = url.pathname === "/demo/" ? "index.html" : url.pathname.replace(/^\/demo\//, "");
  const found = url.pathname.startsWith("/demo/") ? demoPages.get(name) : undefined;
  if (!found) return false;
  response.writeHead(200, HTML).end(found);
  return true;
}

function blocked(url, response) {
  if (url.pathname !== "/") return false;
  response.writeHead(200, HTML).end(blockedPage);
  return true;
}

createServer(serve(shop)).listen(port, "0.0.0.0", () => {
  console.log(`Demo shop on port ${String(port)}, embedding from ${widgetUrl}`);
});
if (blockedPort) {
  createServer(serve(blocked)).listen(blockedPort, "0.0.0.0", () => {
    console.log(`Disallowed-origin demo page on port ${String(blockedPort)}`);
  });
}
