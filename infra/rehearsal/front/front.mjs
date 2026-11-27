// The rehearsal's front end (spec 23, ticket 23-04): a small proxy that publishes Floci's port and runs the Studio's
// SPA fallback CloudFront Function, which Floci 2.5.0 stores but never runs. On AWS the function runs on the
// distribution's default behaviour only, so a deep link such as /projects/abc loads index.html while /api/* and the
// other ordered behaviours keep their own answers, 404s included. The front end does the same for requests to an
// emulated distribution (<id>.cloudfront.localhost), with the very file Terraform uploads, and passes every other
// request (S3, the registry, the AWS APIs) to Floci untouched. It exists only for the rehearsal; nothing on AWS
// changes.
import http from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

// The cdn module's ordered cache behaviours (local.dynamic_paths and local.static_paths): CloudFront routes these
// before the default behaviour, so the function never sees them. A test keeps the two lists equal.
export const ORDERED_PATH_PATTERNS = ["/api/*", "/widget/a/*", "/embed.js", "/widget/assets/*"];

const DISTRIBUTION_HOST = /^[a-z0-9]+\.cloudfront\.localhost(:\d+)?$/;
const ordered = ORDERED_PATH_PATTERNS.map(
  (pattern) => new RegExp(`^${pattern.split("*").map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".*")}$`),
);

// CloudFront Functions are plain scripts with a top-level handler, so the file is evaluated and its handler taken.
const functionPath = fileURLToPath(new URL("../../modules/cdn/functions/spa-fallback.js", import.meta.url));
const sandbox = {};
vm.runInNewContext(`${readFileSync(functionPath, "utf8")}\nthis.handler = handler;`, sandbox, { filename: functionPath });
const spaFallback = sandbox.handler;

// viewerRequest <host> <url>: what CloudFront would do before choosing an origin. Returns { url } to forward, or
// { response } when the function answers itself (the /demo redirect).
function viewerRequest(host, url) {
  const query = url.indexOf("?");
  const uri = query === -1 ? url : url.slice(0, query);
  if (!DISTRIBUTION_HOST.test(host) || ordered.some((pattern) => pattern.test(uri))) return { url };
  const result = spaFallback({ version: "1.0", context: { eventType: "viewer-request" }, request: { method: "GET", uri, headers: {} } });
  if (result.statusCode) return { response: result };
  return { url: result.uri + (query === -1 ? "" : url.slice(query)) };
}

// startFront { port, host, upstream }: listens and resolves to the server once it is listening.
export function startFront({ port, host, upstream }) {
  const target = new URL(upstream);
  const server = http.createServer((req, res) => {
    const decision = viewerRequest(req.headers.host, req.url);
    if (decision.response) {
      const headers = Object.fromEntries(Object.entries(decision.response.headers).map(([name, { value }]) => [name, value]));
      res.writeHead(decision.response.statusCode, headers);
      res.end();
      return;
    }
    const client = req.socket.remoteAddress.replace(/^::ffff:/, "");
    const forwarded = req.headers["x-forwarded-for"];
    const headers = { ...req.headers, "x-forwarded-for": forwarded ? `${forwarded}, ${client}` : client };
    const proxied = http.request(
      { host: target.hostname, port: target.port, method: req.method, path: decision.url, headers, setHost: false },
      (answer) => {
        res.writeHead(answer.statusCode, answer.rawHeaders);
        answer.pipe(res);
      },
    );
    proxied.on("error", (error) => {
      res.writeHead(502, { "content-type": "text/plain" });
      res.end(`Floci did not answer: ${error.message}\n`);
    });
    req.pipe(proxied);
  });
  return new Promise((resolve) => server.listen(port, host, () => resolve(server)));
}
