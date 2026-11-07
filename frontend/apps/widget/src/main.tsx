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

createRoot(root).render(
  <StrictMode>
    <Widget boot={JSON.parse(boot.textContent) as Boot} />
  </StrictMode>,
);
