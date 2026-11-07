import { screen } from "@testing-library/react";

const BOOT = {
  agent: "agt_hr",
  name: "HR helper",
  bootstrap_token: "t",
  theme: { mode: "auto", launcher_type: "bubble", launcher_position: "bottom-right", font: "Inter" },
  logo_url: null,
  avatar_url: null,
  greeting: "Hello!",
  starter_questions: [],
  ui_text: { send_button: null, rate_conversation: null, unavailable_message: null },
  citations: true,
};

function shell(search: string) {
  window.history.replaceState(null, "", `/widget/a/agt_hr${search}`);
  document.body.innerHTML = `<div id="root"></div><script id="widget-boot" type="application/json">${JSON.stringify(BOOT)}</script>`;
}

beforeEach(() => {
  vi.resetModules();
  document.head.innerHTML = "";
});

test("mounts the widget with what the shell hands it, as the snippet's Launcher", async () => {
  shell("?launcher=inline&host=https%3A%2F%2Fwww.example.com");

  await import("./main");

  expect(await screen.findByRole("heading", { name: "HR helper" })).toBeInTheDocument();
  expect(screen.getByText("Hello!")).toBeInTheDocument();
  expect(document.head.querySelector("style")?.textContent).toContain(".widget");
});

test("without a launcher in the address the Theme's applies", async () => {
  shell("?launcher=popup");

  await import("./main");

  expect(await screen.findByRole("button", { name: "Open chat" })).toBeInTheDocument();
});

test("explains what is missing when the shell has no boot data", async () => {
  document.body.innerHTML = '<div id="root"></div>';

  await expect(import("./main")).rejects.toThrow("The widget needs the shell's #root and #widget-boot elements.");
});
