import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MarkdownEditor } from "./MarkdownEditor";

/**
 * Markdown the editor writes back exactly as it was given: load it into the rich editor, make an
 * edit and undo it by hand, and the markdown the editor writes is the text it was given.
 */
const ROUND_TRIPS: [string, string][] = [
  ["headings", "# Role\n\n## Tone\n\n###### Small print"],
  ["paragraphs and soft breaks", "First paragraph.\n\nSecond paragraph,\nsame paragraph."],
  ["a soft break in the paragraph being edited", "First line,\nsame paragraph."],
  ["a hard break", "Line one  \nline two"],
  ["a bulleted list", "- Cite the handbook\n- Be brief\n- Say when you don't know"],
  ["a numbered list", "1. Greet\n2. Answer\n3. Offer help"],
  ["a nested list", "- Leave\n  - Annual\n  - Sick\n- Pay"],
  ["inline code", "Call `escalate()` when stuck."],
  ["a fenced code block", "```\nplain code\n```"],
  ["a fenced code block with a language", "```python\nif a < b and c > d:\n    print('&')\n```"],
  ["a link", "See [the handbook](https://example.com/handbook)."],
  ["a link with a title", '[Policy](https://example.com/policy "Leave policy")'],
  ["bold and italic", "Answer **briefly** and *politely*, ***always***."],
  ["a blockquote", "> Quote the policy word for word."],
  ["a horizontal rule", "Above\n\n---\n\nBelow"],
  ["escaped markdown characters", "Write \\*literally\\* and \\_this\\_."],
  ["prompt tags and ampersands", "<context>\nUse only this & nothing else.\n</context>"],
  ["template variables and code-like words", "Hello {{visitor_name}}, see snake_case_name and [x] or 2 < 3 > 1."],
  ["text that only looks like a table or a task", "| a | b |\n|---|---|\n\n- [ ] not a task"],
  ["a bare URL", "Visit https://example.com/help today."],
  ["a trailing newline", "# Rules\n\nBe kind.\n"],
];

/** Markdown with more than one spelling; once edited, the editor writes the canonical one shown. */
const NORMALISED: [string, string, string][] = [
  ["star bullets become dashes", "* one\n* two", "- one\n- two"],
  ["underscore emphasis becomes stars", "__bold__ and _italic_", "**bold** and *italic*"],
  ["parenthesised numbers become dots", "1) one", "1. one"],
  ["underlined headings become hashes", "Title\n=====", "# Title"],
  ["indented code becomes fenced", "    code", "```\ncode\n```"],
  ["a list straight after a paragraph gets a blank line", "Rules:\n- one", "Rules:\n\n- one"],
  ["HTML entities are decoded", "&lt;b&gt; &amp;", "<b> &"],
];

async function openMarkdownView(label: string) {
  await userEvent.setup().click(screen.getByRole("button", { name: "Markdown" }));
  return screen.getByRole("textbox", { name: `${label} (Markdown)` });
}

/** The markdown the rich editor writes for what it holds: type a character, then delete it. */
async function writtenByTheRichEditor(label: string, onChange: ReturnType<typeof vi.fn>) {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("textbox", { name: label }));
  await user.keyboard("x{Backspace}");
  return onChange.mock.lastCall?.[0] as string;
}

test.each(ROUND_TRIPS)("%s round-trip exactly", async (_name, markdown) => {
  const onChange = vi.fn();
  render(<MarkdownEditor label="System prompt" defaultValue={markdown} onChange={onChange} />);

  expect(await writtenByTheRichEditor("System prompt", onChange)).toBe(markdown);
});

test.each(NORMALISED)("%s", async (_name, markdown, canonical) => {
  const onChange = vi.fn();
  render(<MarkdownEditor label="Prompt" defaultValue={markdown} onChange={onChange} />);

  expect(await writtenByTheRichEditor("Prompt", onChange)).toBe(canonical);
});

test("an empty editor stores nothing until something is typed", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const { container } = render(<MarkdownEditor label="Prompt" name="prompt" defaultValue="" onChange={onChange} />);
  const editor = await screen.findByRole("textbox", { name: "Prompt" });
  expect(container.querySelector("input[name=prompt]")).toHaveValue("");

  await user.click(editor);
  await user.keyboard("Hi");

  expect(onChange).toHaveBeenLastCalledWith("Hi");
});

test("the rich editor shows the markdown formatted", async () => {
  render(<MarkdownEditor label="Prompt" defaultValue={"# Role\n\nBe **brief**.\n\n- Cite [sources](https://example.com)"} />);

  const editor = await screen.findByRole("textbox", { name: "Prompt" });
  expect(within(editor).getByRole("heading", { level: 1, name: "Role" })).toBeInTheDocument();
  expect(within(editor).getByText("brief").tagName).toBe("STRONG");
  expect(within(editor).getByRole("listitem")).toHaveTextContent("Cite sources");
  expect(within(editor).getByRole("link", { name: "sources" })).toHaveAttribute("href", "https://example.com");
});

test("loading markdown changes nothing until it is edited", async () => {
  const onChange = vi.fn();
  // A spelling the editor would normalise, with a value a form would submit.
  const { container } = render(<MarkdownEditor label="Prompt" name="prompt" defaultValue="* one" onChange={onChange} />);
  await screen.findByRole("textbox", { name: "Prompt" });

  expect(onChange).not.toHaveBeenCalled();
  expect(container.querySelector("input[name=prompt]")).toHaveValue("* one");
});

test("formatting from the toolbar is stored as markdown", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<MarkdownEditor label="Prompt" defaultValue="Rules" onChange={onChange} />);
  const editor = await screen.findByRole("textbox", { name: "Prompt" });
  const toolbar = screen.getByRole("toolbar", { name: "Prompt formatting" });

  await user.click(within(toolbar).getByRole("button", { name: "Heading" }));
  expect(onChange).toHaveBeenLastCalledWith("## Rules");
  expect(within(toolbar).getByRole("button", { name: "Heading" })).toHaveAttribute("aria-pressed", "true");
  await user.click(within(toolbar).getByRole("button", { name: "Heading" }));
  expect(onChange).toHaveBeenLastCalledWith("Rules");

  await user.click(within(toolbar).getByRole("button", { name: "Bulleted list" }));
  expect(onChange).toHaveBeenLastCalledWith("- Rules");
  await user.click(within(toolbar).getByRole("button", { name: "Numbered list" }));
  expect(onChange).toHaveBeenLastCalledWith("1. Rules");
  await user.click(within(toolbar).getByRole("button", { name: "Numbered list" }));
  expect(onChange).toHaveBeenLastCalledWith("Rules");

  await user.click(within(toolbar).getByRole("button", { name: "Code block" }));
  expect(onChange).toHaveBeenLastCalledWith("```\nRules\n```");
  await user.click(within(toolbar).getByRole("button", { name: "Code block" }));

  await user.click(editor);
  await user.keyboard("{Control>}a{/Control}");
  await user.click(within(toolbar).getByRole("button", { name: "Bold" }));
  expect(onChange).toHaveBeenLastCalledWith("**Rules**");
  await user.click(within(toolbar).getByRole("button", { name: "Italic" }));
  expect(onChange).toHaveBeenLastCalledWith("***Rules***");
  await user.click(within(toolbar).getByRole("button", { name: "Bold" }));
  await user.click(within(toolbar).getByRole("button", { name: "Italic" }));
  await user.click(within(toolbar).getByRole("button", { name: "Inline code" }));
  expect(onChange).toHaveBeenLastCalledWith("`Rules`");
});

test("text typed in the Markdown view is stored exactly and shown formatted", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const { container } = render(
    <MarkdownEditor label="Prompt" name="prompt" defaultValue="Old" maxLength={200} onChange={onChange} />,
  );
  await screen.findByRole("textbox", { name: "Prompt" });

  const source = await openMarkdownView("Prompt");
  expect(screen.getByRole("button", { name: "Markdown" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  expect(source).toHaveAttribute("maxlength", "200");
  await user.clear(source);
  // A spelling the rich editor would normalise is still stored as typed.
  await user.type(source, "* Be __kind__");
  expect(onChange).toHaveBeenLastCalledWith("* Be __kind__");
  expect(container.querySelector("input[name=prompt]")).toHaveValue("* Be __kind__");

  await user.click(screen.getByRole("button", { name: "Markdown" }));
  const editor = screen.getByRole("textbox", { name: "Prompt" });
  expect(within(editor).getByRole("listitem")).toHaveTextContent("Be kind");
  expect(within(editor).getByText("kind").tagName).toBe("STRONG");
  // Switching back is not an edit.
  expect(onChange).toHaveBeenLastCalledWith("* Be __kind__");
  expect(container.querySelector("input[name=prompt]")).toHaveValue("* Be __kind__");
});

test("a rich edit keeps the trailing newline the markdown had", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<MarkdownEditor label="Prompt" defaultValue={"Rules\n"} onChange={onChange} />);
  await screen.findByRole("textbox", { name: "Prompt" });

  await user.click(screen.getByRole("button", { name: "Heading" }));

  expect(onChange).toHaveBeenLastCalledWith("## Rules\n");
});

test("a disabled editor can't be changed", async () => {
  render(<MarkdownEditor label="Prompt" defaultValue="Read only" disabled />);

  const editor = await screen.findByRole("textbox", { name: "Prompt" });
  expect(editor).toHaveAttribute("contenteditable", "false");
  expect(screen.getByRole("button", { name: "Bold" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Markdown" })).toBeDisabled();
});

test("an editor follows its disabled prop after it is created", async () => {
  const { rerender } = render(<MarkdownEditor label="Prompt" defaultValue="Rules" />);
  const editor = await screen.findByRole("textbox", { name: "Prompt" });
  expect(editor).toHaveAttribute("contenteditable", "true");

  // Archived while open: nothing can be typed any more.
  rerender(<MarkdownEditor label="Prompt" defaultValue="Rules" disabled />);
  expect(editor).toHaveAttribute("contenteditable", "false");
  expect(screen.getByRole("button", { name: "Bold" })).toBeDisabled();

  // Restored: it can be edited again.
  rerender(<MarkdownEditor label="Prompt" defaultValue="Rules" />);
  expect(editor).toHaveAttribute("contenteditable", "true");
  expect(screen.getByRole("button", { name: "Bold" })).toBeEnabled();
});

test("the Markdown view follows its disabled prop after it is opened", async () => {
  const { rerender } = render(<MarkdownEditor label="Prompt" defaultValue="Rules" />);
  await screen.findByRole("textbox", { name: "Prompt" });
  const source = await openMarkdownView("Prompt");
  expect(source).toBeEnabled();

  // Archived while the Markdown view is open: the text can't be changed there either.
  rerender(<MarkdownEditor label="Prompt" defaultValue="Rules" disabled />);
  expect(screen.getByRole("textbox", { name: "Prompt (Markdown)" })).toBeDisabled();

  // Restored: it can be edited again.
  rerender(<MarkdownEditor label="Prompt" defaultValue="Rules" />);
  expect(screen.getByRole("textbox", { name: "Prompt (Markdown)" })).toBeEnabled();
});

test("the Markdown view opens on the stored text, not the editor's rewrite of it", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<MarkdownEditor label="Prompt" defaultValue={"* a\n* __b__"} onChange={onChange} />);
  await screen.findByRole("textbox", { name: "Prompt" });

  const source = await openMarkdownView("Prompt");
  expect(source).toHaveValue("* a\n* __b__");
  await user.type(source, "c");

  expect(onChange).toHaveBeenLastCalledWith("* a\n* __b__c");
});

test("the character count shows how far the markdown is from the limit", async () => {
  const user = userEvent.setup();
  render(<MarkdownEditor label="Prompt" defaultValue="Rules" maxLength={8} />);
  const editor = await screen.findByRole("textbox", { name: "Prompt" });

  expect(screen.getByText("5 / 8 characters")).toBeInTheDocument();
  expect(editor).not.toHaveAttribute("aria-invalid");

  await user.click(editor);
  await user.keyboard("more ");
  // The formatted view can't refuse keystrokes, so it says the text is too long instead.
  expect(screen.getByText("10 / 8 characters: 2 too many")).toBeInTheDocument();
  expect(editor).toHaveAttribute("aria-invalid", "true");
  expect(editor).toHaveAccessibleDescription("10 / 8 characters: 2 too many");
});

test("no character count without a limit", async () => {
  render(<MarkdownEditor label="Prompt" defaultValue="Rules" />);
  await screen.findByRole("textbox", { name: "Prompt" });

  expect(screen.queryByText(/characters/)).not.toBeInTheDocument();
});
