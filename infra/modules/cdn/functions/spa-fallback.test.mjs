// Behaviour of the Studio's SPA fallback CloudFront Function (ticket 09-05), run in Node against the exact file
// Terraform uploads. CloudFront Functions are plain scripts with a top-level `handler`, not modules, so the test
// evaluates the file and takes `handler` from it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const path = fileURLToPath(new URL("./spa-fallback.js", import.meta.url));
const sandbox = {};
vm.runInNewContext(`${readFileSync(path, "utf8")}\nthis.handler = handler;`, sandbox, { filename: path });
const { handler } = sandbox;

const viewerRequest = (uri, querystring = {}) => ({
  version: "1.0",
  context: { eventType: "viewer-request" },
  request: { method: "GET", uri, querystring, headers: { host: { value: "d111111abcdef8.cloudfront.net" } }, cookies: {} },
});

test("a deep link to a Studio route loads the Studio's index.html", () => {
  assert.equal(handler(viewerRequest("/projects/abc/agents")).uri, "/index.html");
});

test("the root loads index.html", () => {
  assert.equal(handler(viewerRequest("/")).uri, "/index.html");
});

test("a route with a trailing slash loads index.html", () => {
  assert.equal(handler(viewerRequest("/settings/")).uri, "/index.html");
});

test("a request for a file is passed through unchanged, so a missing asset is a 404, not HTML", () => {
  assert.equal(handler(viewerRequest("/assets/index-3f2a9c.js")).uri, "/assets/index-3f2a9c.js");
  assert.equal(handler(viewerRequest("/favicon.ico")).uri, "/favicon.ico");
  assert.equal(handler(viewerRequest("/index.html")).uri, "/index.html");
});

test("a dot in an earlier path segment does not make a route a file", () => {
  assert.equal(handler(viewerRequest("/v1.2/projects")).uri, "/index.html");
});

test("the rest of the request (method, query string, headers, cookies) is untouched", () => {
  const before = viewerRequest("/projects", { tab: { value: "documents" } }).request;
  const after = handler(viewerRequest("/projects", { tab: { value: "documents" } }));
  assert.deepEqual({ ...after, uri: before.uri }, before);
});
