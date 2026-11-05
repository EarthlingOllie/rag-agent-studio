import { randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

/**
 * An in-process stand-in for the Studio and API, used only to check the shared fixtures.
 * It speaks the same health routes as the real API and the auth routes the fixtures call.
 */
export interface FakeStudioOptions {
  /** Health requests answered 503 before the API reports healthy. */
  apiUnhealthyFor?: number;
  /** When false, the worker never replies. */
  workerHealthy?: boolean;
}

export interface FakeStudio {
  url: string;
  healthRequests: () => number;
  close: () => Promise<void>;
}

interface Account {
  email: string;
  password: string;
}

function json(response: ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}) {
  response.writeHead(status, { "content-type": "application/json", ...headers });
  response.end(JSON.stringify(body));
}

function html(response: ServerResponse, body: string) {
  response.writeHead(200, { "content-type": "text/html" });
  response.end(`<!doctype html><html lang="en"><head><title>Fake Studio</title></head><body><main>${body}</main></body></html>`);
}

async function readJson(request: IncomingMessage): Promise<Record<string, string>> {
  let raw = "";
  for await (const chunk of request) raw += String(chunk);
  return JSON.parse(raw) as Record<string, string>;
}

function sessionToken(request: IncomingMessage): string | undefined {
  const cookies = request.headers.cookie?.split(";").map((part) => part.trim()) ?? [];
  return cookies.find((cookie) => cookie.startsWith("session="))?.slice("session=".length);
}

export async function startFakeStudio(options: FakeStudioOptions = {}): Promise<FakeStudio> {
  const { apiUnhealthyFor = 0, workerHealthy = true } = options;
  const accounts = new Map<string, Account>();
  const sessions = new Map<string, string>();
  let healthRequests = 0;

  const server = createServer((request, response) => {
    void (async () => {
      const route = `${request.method ?? "GET"} ${request.url ?? "/"}`;
      switch (route) {
        case "GET /":
          html(response, "<h1>Fake Studio</h1>");
          return;
        case "GET /api/health": {
          healthRequests += 1;
          const healthy = healthRequests > apiUnhealthyFor;
          const check = healthy ? "ok" : "error";
          json(response, healthy ? 200 : 503, { status: check, checks: { database: check, redis: check } });
          return;
        }
        case "GET /api/health/worker":
          json(response, workerHealthy ? 200 : 503, workerHealthy ? { status: "ok", reply: "pong" } : { status: "error", reply: null });
          return;
        case "POST /api/auth/sign-up": {
          const body = await readJson(request);
          const email = String(body.email);
          if (accounts.has(email)) {
            json(response, 409, { detail: "Email already registered" });
            return;
          }
          accounts.set(email, { email, password: String(body.password) });
          json(response, 201, { email });
          return;
        }
        case "POST /api/auth/sign-in": {
          const body = await readJson(request);
          const account = accounts.get(String(body.email));
          if (account === undefined || account.password !== body.password) {
            json(response, 401, { detail: "Email or password is incorrect" });
            return;
          }
          const token = randomUUID();
          sessions.set(token, account.email);
          json(response, 200, { email: account.email }, { "set-cookie": `session=${token}; HttpOnly; Path=/; SameSite=Lax` });
          return;
        }
        case "GET /whoami": {
          const token = sessionToken(request);
          const email = token === undefined ? undefined : sessions.get(token);
          html(response, email === undefined ? "<h1>Signed out</h1>" : `<h1>Signed in as ${email}</h1>`);
          return;
        }
        default:
          json(response, 404, { detail: "Not found" });
      }
    })();
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;

  return {
    url: `http://127.0.0.1:${String(port)}`,
    healthRequests: () => healthRequests,
    close: () =>
      new Promise<void>((resolve, reject) => {
        server.close((error) => {
          if (error) reject(error);
          else resolve();
        });
      }),
  };
}
