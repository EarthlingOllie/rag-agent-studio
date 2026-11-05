import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChatWindow, Composer, MessageBubble, ThemeScope } from "./primitives";
import { DEFAULT_THEME } from "./theme";

test("the primitives read the Theme from the scope's custom properties", () => {
  render(
    <ThemeScope theme={{ ...DEFAULT_THEME, radius: 2 }} scheme="dark" label="Widget">
      <ChatWindow agentName="Ada" composer={<Composer onSend={() => undefined} />}>
        <MessageBubble from="visitor">Hello</MessageBubble>
      </ChatWindow>
    </ThemeScope>,
  );

  const scope = screen.getByRole("group", { name: "Widget" });
  expect(scope.style.getPropertyValue("--theme-primary")).toBe("#818cf8");
  expect(scope.style.getPropertyValue("--theme-radius")).toBe("2px");
  const chat = within(scope).getByRole("region", { name: "Chat with Ada" });
  expect(within(chat).getByRole("heading", { name: "Ada" })).toBeInTheDocument();
  // jsdom doesn't resolve var(), so the declarations themselves are checked.
  const visitorMessage = within(chat).getByText("Hello").style;
  expect([visitorMessage.background, visitorMessage.color, visitorMessage.borderRadius]).toEqual([
    "var(--theme-primary)",
    "var(--theme-on-primary)",
    "var(--theme-radius)",
  ]);
});

test("the Composer sends the typed Message and clears the box", async () => {
  const sent: string[] = [];
  render(<Composer onSend={(message) => sent.push(message)} />);

  await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "Opening hours?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(sent).toEqual(["Opening hours?"]);
  expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
});
