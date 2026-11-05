import "./index.css";

import { QueryClient } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { createAppRouter } from "./router";

const root = document.getElementById("root");
if (!root) {
  throw new Error("The Studio needs a #root element to mount into.");
}

createRoot(root).render(
  <StrictMode>
    <App router={createAppRouter()} queryClient={new QueryClient()} />
  </StrictMode>,
);
