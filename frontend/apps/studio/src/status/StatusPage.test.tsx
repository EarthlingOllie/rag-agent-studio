import type { Schemas } from "@studio/api-client";
import { screen, within } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";

import { renderStudio } from "../test/render";
import { server } from "../test/server";

function statusOf(name: string) {
  return within(screen.getByRole("row", { name: new RegExp(`^${name}`) })).getAllByRole("cell")[0];
}

test("shows every part of the stack as operational when the API is healthy", async () => {
  renderStudio("/status");

  expect(await screen.findByText("All systems operational")).toBeInTheDocument();
  expect(statusOf("API")).toHaveTextContent("OK");
  expect(statusOf("Database")).toHaveTextContent("OK");
  expect(statusOf("Redis")).toHaveTextContent("OK");
  expect(await screen.findByText("Worker replied: pong")).toBeInTheDocument();
  expect(statusOf("Worker")).toHaveTextContent("OK");
});

test("names the failing dependency when the API reports it unhealthy", async () => {
  const degraded: Schemas["HealthResponse"] = {
    status: "error",
    checks: { database: "error", redis: "ok" },
  };
  server.use(http.get("*/api/health", () => HttpResponse.json(degraded, { status: 503 })));

  renderStudio("/status");

  expect(await screen.findByText("Some systems are unavailable")).toBeInTheDocument();
  expect(statusOf("Database")).toHaveTextContent("Unavailable");
  expect(statusOf("Redis")).toHaveTextContent("OK");
});

test("shows the worker as unavailable when it does not reply", async () => {
  const silent: Schemas["WorkerHealthResponse"] = { status: "error", reply: null };
  server.use(http.get("*/api/health/worker", () => HttpResponse.json(silent, { status: 503 })));

  renderStudio("/status");

  expect(await screen.findByText("Worker did not reply")).toBeInTheDocument();
  expect(statusOf("Worker")).toHaveTextContent("Unavailable");
  expect(screen.getByRole("status")).toHaveTextContent("Some systems are unavailable");
});

test("says the API cannot be reached when the request fails", async () => {
  server.use(
    http.get("*/api/health", () => HttpResponse.error()),
    http.get("*/api/health/worker", () => HttpResponse.error()),
  );

  renderStudio("/status");

  expect(await screen.findByText("The API could not be reached")).toBeInTheDocument();
  expect(statusOf("API")).toHaveTextContent("Unavailable");
  expect(await screen.findByText("Worker did not reply")).toBeInTheDocument();
});

test("treats an unexpected API response as unavailable", async () => {
  server.use(http.get("*/api/health", () => new HttpResponse("Bad gateway", { status: 502 })));

  renderStudio("/status");

  expect(await screen.findByText("The API could not be reached")).toBeInTheDocument();
});

test("shows a checking state while the first health request is in flight", async () => {
  server.use(http.get("*/api/health", () => delay("infinite")));

  renderStudio("/status");

  expect(await screen.findByRole("status")).toHaveTextContent("Checking…");
  expect(statusOf("API")).toHaveTextContent("Checking…");
  expect(statusOf("Database")).toHaveTextContent("Checking…");
});
