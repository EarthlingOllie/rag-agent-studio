// The demo host page: a stand-in for an Organisation's website, served by `docker compose` on
// its own origin (port 5175) so the widget is embedded cross-origin for real. It pastes the
// Embed Snippet for the Agent named by `?agent=agt_…`, loading `embed.js` from WIDGET_URL (the
// Studio's origin, where the platform serves the loader). `&launcher=inline` puts the widget in
// the page's #chat container and `&launcher=bubble` asks for the bubble; without it the
// Theme's Launcher applies. No dependencies: plain Node.
import { createServer } from "node:http";

const port = Number(process.env.PORT ?? 5175);
const widgetUrl = (process.env.WIDGET_URL ?? "http://localhost:5173").replace(/\/$/, "");

function escape(text) {
  return text.replace(/[&<>"']/g, (c) => `&#${String(c.charCodeAt(0))};`);
}

function page(agent, launcher) {
  const layout =
    launcher === "inline" ? ' data-launcher="inline" data-target="#chat"' : launcher === "bubble" ? ' data-launcher="bubble"' : "";
  const snippet = agent
    ? `<script src="${escape(widgetUrl)}/embed.js" data-agent="${escape(agent)}"${layout} async></script>`
    : "<p>Add <code>?agent=</code> and an Agent's public ID to the address to embed it.</p>";
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

createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://host");
  if (url.pathname === "/health") {
    response.writeHead(200, { "Content-Type": "text/plain" }).end("ok");
    return;
  }
  if (url.pathname !== "/") {
    response.writeHead(404, { "Content-Type": "text/plain" }).end("Not found");
    return;
  }
  const agent = url.searchParams.get("agent") ?? "";
  response
    .writeHead(200, { "Content-Type": "text/html; charset=utf-8" })
    .end(page(/^[A-Za-z0-9_-]{1,64}$/.test(agent) ? agent : "", url.searchParams.get("launcher")));
}).listen(port, "0.0.0.0", () => {
  console.log(`Demo host page on port ${String(port)}, embedding from ${widgetUrl}`);
});
