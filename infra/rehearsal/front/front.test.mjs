// Behaviour of the rehearsal's front end (ticket 23-04): the proxy in front of Floci that runs the Studio's SPA fallback
// CloudFront Function, which Floci stores but does not run. Each test starts the front end against a stand-in for
// Floci and makes real HTTP requests through it.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { startFront, ORDERED_PATH_PATTERNS } from "./front.mjs";

const studio = "egyk4lut4xh5sr.cloudfront.localhost:4566";
const servers = [];
after(() => servers.forEach((s) => s.close()));

// A stand-in for Floci: records each request and answers 404 JSON for /api/*, the path otherwise.
const upstream = await new Promise((resolve) => {
  const seen = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body });
      if (req.url.startsWith("/api/")) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end('{"detail":"Not Found"}');
        return;
      }
      res.writeHead(200, { "content-type": "text/plain", "x-upstream": "floci" });
      res.end(`served ${req.url}`);
    });
  });
  servers.push(server);
  server.listen(0, "127.0.0.1", () => resolve({ seen, url: `http://127.0.0.1:${server.address().port}` }));
});

const front = await startFront({ port: 0, host: "127.0.0.1", upstream: upstream.url });
servers.push(front);
const frontPort = front.address().port;

// request <host> <path> [options]: a request through the front end; resolves to { status, headers, body, seen }.
function request(host, path, { method = "GET", headers = {}, body, port = frontPort } = {}) {
  return new Promise((resolve, reject) => {
    const before = upstream.seen.length;
    const req = http.request({ host: "127.0.0.1", port, method, path, headers: { host, ...headers } }, (res) => {
      let text = "";
      res.on("data", (c) => (text += c));
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body: text, seen: upstream.seen.slice(before) }));
    });
    req.on("error", reject);
    req.end(body);
  });
}

test("a Studio deep link reaches Floci as /index.html, so a refresh loads the Studio", async () => {
  const res = await request(studio, "/projects/abc/agents");
  assert.equal(res.seen[0].url, "/index.html");
  assert.equal(res.status, 200);
  assert.equal(res.body, "served /index.html");
});

test("the query string of a deep link is kept", async () => {
  const res = await request(studio, "/accept-invite?token=t0k");
  assert.equal(res.seen[0].url, "/index.html?token=t0k");
});

test("an API 404 survives: /api/* is its own behaviour on CloudFront and is never rewritten", async () => {
  const res = await request(studio, "/api/smoke-check-not-found");
  assert.equal(res.seen[0].url, "/api/smoke-check-not-found");
  assert.equal(res.status, 404);
  assert.equal(res.headers["content-type"], "application/json");
  assert.equal(res.body, '{"detail":"Not Found"}');
});

test("the widget shell, the widget's assets and embed.js are never rewritten", async () => {
  for (const path of ["/widget/a/smoke-check", "/widget/assets/app-1a2b.js", "/embed.js"]) {
    const res = await request(studio, path);
    assert.equal(res.seen[0].url, path);
  }
});

test("a missing asset is passed through, so it stays a 404 rather than HTML", async () => {
  const res = await request(studio, "/assets/index-3f2a9c.js");
  assert.equal(res.seen[0].url, "/assets/index-3f2a9c.js");
});

test("/demo is redirected by the function itself, without reaching Floci", async () => {
  const res = await request(studio, "/demo");
  assert.equal(res.status, 301);
  assert.equal(res.headers.location, "/demo/");
  assert.equal(res.seen.length, 0);
});

test("requests for Floci's own services (S3, the registry, the APIs) pass through untouched", async () => {
  const res = await request("localhost:4566", "/studio-local-documents/projects/p1/file?X-Amz-Signature=abc", {
    method: "PUT",
    headers: { "content-type": "text/markdown" },
    body: "# Hello",
  });
  assert.equal(res.seen[0].url, "/studio-local-documents/projects/p1/file?X-Amz-Signature=abc");
  assert.equal(res.seen[0].method, "PUT");
  assert.equal(res.seen[0].body, "# Hello");
  assert.equal(res.seen[0].headers.host, "localhost:4566");
  assert.equal(res.headers["x-upstream"], "floci");
});

test("the Host header and method reach Floci unchanged, and the client's address is added to X-Forwarded-For", async () => {
  const res = await request(studio, "/api/auth/sign-in", { method: "POST", headers: { "x-forwarded-for": "203.0.113.9" }, body: "{}" });
  assert.equal(res.seen[0].method, "POST");
  assert.equal(res.seen[0].headers.host, studio);
  assert.equal(res.seen[0].headers["x-forwarded-for"], "203.0.113.9, 127.0.0.1");
});

test("without an X-Forwarded-For the client's address starts one", async () => {
  const res = await request(studio, "/api/health");
  assert.equal(res.seen[0].headers["x-forwarded-for"], "127.0.0.1");
});

test("/demo/ loads the demo pages' index, as the function says", async () => {
  const res = await request(studio, "/demo/");
  assert.equal(res.seen[0].url, "/demo/index.html");
});

test("the front end answers 502 when Floci does not answer", async () => {
  const dead = await startFront({ port: 0, host: "127.0.0.1", upstream: "http://127.0.0.1:9" });
  servers.push(dead);
  const res = await request(studio, "/projects", { port: dead.address().port });
  assert.equal(res.status, 502);
  assert.match(res.body, /Floci did not answer/);
});

test("the paths it leaves alone are exactly the cdn module's ordered cache behaviours", () => {
  const main = readFileSync(fileURLToPath(new URL("../../modules/cdn/main.tf", import.meta.url)), "utf8");
  const list = (name) => JSON.parse(main.match(new RegExp(`${name}\\s*=\\s*(\\[[^\\]]*\\])`))[1]);
  assert.deepEqual([...ORDERED_PATH_PATTERNS].sort(), [...list("dynamic_paths"), ...list("static_paths")].sort());
});

test("run as a program it listens on FRONT_PORT and forwards to FLOCI_URL", async () => {
  const child = spawn(process.execPath, [fileURLToPath(new URL("./main.mjs", import.meta.url))], {
    env: { ...process.env, FRONT_PORT: "0", FRONT_HOST: "127.0.0.1", FLOCI_URL: upstream.url },
  });
  try {
    const port = await new Promise((resolve) => child.stdout.once("data", (d) => resolve(Number(String(d).match(/:(\d+)/)[1]))));
    const res = await request(studio, "/settings", { port });
    assert.equal(res.seen[0].url, "/index.html");
  } finally {
    child.kill();
  }
});
