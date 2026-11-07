import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import type { Boot } from "./chat";
import { STYLES } from "./styles";
import { Widget } from "./Widget";

const root = document.getElementById("root");
const boot = document.getElementById("widget-boot");
if (!root || !boot) {
  throw new Error("The widget needs the shell's #root and #widget-boot elements.");
}

const style = document.createElement("style");
style.textContent = STYLES;
document.head.append(style);

// The loader passes the snippet's `data-launcher`, if any, and the host page's origin.
const params = new URLSearchParams(window.location.search);
const launcher = params.get("launcher");

createRoot(root).render(
  <StrictMode>
    <Widget
      boot={JSON.parse(boot.textContent) as Boot}
      launcher={launcher === "bubble" || launcher === "inline" ? (launcher) : null}
      host={params.get("host")}
    />
  </StrictMode>,
);
