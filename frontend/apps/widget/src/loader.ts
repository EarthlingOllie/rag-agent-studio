// The built `embed.js`: mounts the snippet that loaded it. `currentScript` is only set while
// the script first runs, so it is read here, at the top level.
import { mount } from "./embed";

mount(document.currentScript);
