import "./index.css";

import { QueryClient } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { initAppearance } from "./design";
import { createAppRouter } from "./router";

const root = document.getElementById("root");
if (!root) {
  throw new Error("The Studio needs a #root element to mount into.");
}

// Before the first render, so the page never flashes the other Appearance.
initAppearance();

createRoot(root).render(
  <StrictMode>
    <App router={createAppRouter()} queryClient={new QueryClient()} />
  </StrictMode>,
);
