import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MarkdownEditor } from "./MarkdownEditor";

/**
 * Markdown the editor writes back exactly as it was given: load it into the rich editor, open the
 * Markdown view (the editor's own serialisation of what it holds) and the text is unchanged.
 */
const ROUND_TRIPS: [string, string][] = [
  ["headings", "# Role\n\n## Tone\n\n###### Small print"],
  ["paragraphs and soft breaks", "First paragraph.\n\nSecond paragraph,\nsame paragraph."],
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
  ["nothing at all", ""],
];

/** Markdown with more than one spelling; the editor writes the canonical one shown. */
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

test.each(ROUND_TRIPS)("%s round-trip exactly", async (_name, markdown) => {
  render(<MarkdownEditor label="System prompt" defaultValue={markdown} />);
  await screen.findByRole("textbox", { name: "System prompt" });

  expect(await openMarkdownView("System prompt")).toHaveValue(markdown);
});

test.each(NORMALISED)("%s", async (_name, markdown, canonical) => {
  render(<MarkdownEditor label="Prompt" defaultValue={markdown} />);
  await screen.findByRole("textbox", { name: "Prompt" });

  expect(await openMarkdownView("Prompt")).toHaveValue(canonical);
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
