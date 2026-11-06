import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

import { server } from "./server";

// The first render of a lazily loaded route can take over the default 1 s when the machine is
// busy (the whole suite runs in parallel workers), so `findBy*` and `waitFor` wait up to 5 s.
configure({ asyncUtilTimeout: 5000 });

// jsdom has no layout engine; the router's scroll restoration only needs scrollTo to exist.
window.scrollTo = () => undefined;
// Nor can it measure text: the markdown editor (ProseMirror) asks where the selection is when it
// scrolls it into view. Nothing has a size, so every answer is an empty rectangle.
const emptyRects = () => Object.assign([] as DOMRect[], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects = emptyRects;
Range.prototype.getBoundingClientRect = () => new DOMRect();
Element.prototype.getClientRects = emptyRects;
document.elementFromPoint = () => null;

// The first render of a route loads its modules; on a loaded machine that alone can pass the
// default one second, so `findBy…` and `waitFor` wait up to five before failing.
configure({ asyncUtilTimeout: 5000 });

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});
afterEach(() => {
  server.resetHandlers();
});
afterAll(() => {
  server.close();
});
