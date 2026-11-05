import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
  type RouterHistory,
} from "@tanstack/react-router";

import { StatusPage } from "./status/StatusPage";

function Shell() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <nav className="mx-auto flex max-w-4xl items-center gap-6 px-6 py-4" aria-label="Main">
          <span className="font-semibold">RAG Agent Studio</span>
          <Link to="/" className="text-sm text-slate-600 [&.active]:font-medium [&.active]:text-slate-900">
            System status
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}

const rootRoute = createRootRoute({ component: Shell });
const statusRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: StatusPage });
const routeTree = rootRoute.addChildren([statusRoute]);

export function createAppRouter(history?: RouterHistory) {
  return createRouter(history ? { routeTree, history } : { routeTree });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}
