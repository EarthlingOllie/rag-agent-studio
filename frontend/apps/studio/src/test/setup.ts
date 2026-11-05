import "@testing-library/jest-dom/vitest";

import { server } from "./server";

// jsdom has no layout engine; the router's scroll restoration only needs scrollTo to exist.
window.scrollTo = () => undefined;

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});
afterEach(() => {
  server.resetHandlers();
});
afterAll(() => {
  server.close();
});
