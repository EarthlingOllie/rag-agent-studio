// The end-to-end axe sweep (e2e/tests/accessibility.spec.ts) visits every signed-in page in both
// Appearances from one list, e2e/fixtures/pages.ts. This keeps that list in step with the router:
// a new signed-in page fails here until the sweep visits it.
import { SIGNED_IN_PAGES } from "../../../e2e/fixtures/pages";
import { createAppRouter } from "./router";

test("the axe sweep's page list names every signed-in page the router has, once", () => {
  const router = createAppRouter();
  // Pages are the routes with no children, under the signed-in shell; "/" only redirects.
  const pages = Object.values(router.routesById)
    .filter((route) => route.id.startsWith("/signed-in/") && !Array.isArray(route.children))
    .map((route) => route.fullPath.replace(/(.)\/$/, "$1"))
    .filter((path) => path !== "/")
    .sort();

  const listed = SIGNED_IN_PAGES.map((page) => page.route);
  expect(new Set(listed).size).toBe(listed.length);
  expect([...listed].sort()).toEqual(pages);
});
