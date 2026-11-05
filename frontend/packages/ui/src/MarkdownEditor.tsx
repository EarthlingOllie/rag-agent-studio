import { Markdown } from "@tiptap/markdown";
import { type Editor, EditorContent, useEditor, useEditorState } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Marked, type marked as defaultMarked } from "marked";
import { useId, useRef, useState } from "react";

/**
 * The markdown dialect the editor reads and writes: CommonMark without raw HTML or bare-URL
 * autolinks. Prompts are text for a model, so `<context>`, `&` and URLs stay literal text instead
 * of becoming markup, and GFM extras the editor can't show (tables, task lists, strikethrough)
 * stay as the characters that were typed.
 */
function createMarked(): Marked {
  const marked = new Marked({ gfm: false });
  // Returning nothing from a tokenizer means "no token here": the text tokenizer takes it.
  const none = () => undefined;
  marked.use({ tokenizer: { html: none, tag: none, url: none } });
  return marked;
}

type TextNode = { marks?: { type: string }[] };
type Serialiser = {
  codeTypes: Set<string>;
  escapeMarkdownSyntax(text: string): string;
  encodeTextForMarkdown(text: string, node: TextNode, parent?: { type?: string }): string;
};

/**
 * Text is written back as it was typed whenever that reads back as the same plain text, and only
 * escaped where it would otherwise turn into formatting. TipTap's own writer escapes every `_`,
 * `[` and `~` and turns `<` and `&` into HTML entities, which would change what the model reads.
 */
function writeTextExactly(editor: Editor, marked: Marked) {
  const serialiser = editor.markdown as unknown as Serialiser;
  const isPlain = (text: string) => {
    const tokens = marked.Lexer.lexInline(text, marked.defaults);
    return tokens.length === 1 && tokens[0]?.type === "text" && tokens[0].raw === text;
  };
  const isCode = (node: TextNode, parent?: { type?: string }) =>
    // A Set holds no undefined, so a text node without a parent isn't in code.
    serialiser.codeTypes.has(parent?.type as string) ||
    (node.marks ?? []).some((mark) => serialiser.codeTypes.has(mark.type));
  serialiser.encodeTextForMarkdown = (text, node, parent) =>
    isCode(node, parent) || isPlain(text) ? text : serialiser.escapeMarkdownSyntax(text);
}

/** The whitespace a value ends with; the editor's writer drops it, so it is put back. */
function trailingWhitespace(markdown: string): string {
  return markdown.slice(markdown.trimEnd().length);
}

// Tailwind's reset strips headings and lists of their look; give the formatted view one back.
const FORMATTED = [
  "space-y-2 text-sm",
  "[&_h1]:text-xl [&_h1]:font-semibold [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:font-semibold [&_h4]:font-semibold [&_h5]:font-semibold [&_h6]:font-semibold",
  "[&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6",
  "[&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:font-mono [&_pre]:rounded [&_pre]:bg-slate-100 [&_pre]:p-2",
  "[&_a]:text-blue-800 [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:border-slate-300 [&_blockquote]:pl-3",
].join(" ");

const TOOL =
  "rounded px-2 py-1 text-sm text-slate-800 hover:bg-slate-100 disabled:opacity-50 aria-pressed:bg-slate-200 aria-pressed:font-semibold";

type Tool = { label: string; text: string; isActive: (editor: Editor) => boolean; run: (editor: Editor) => void };

const TOOLS: Tool[] = [
  {
    label: "Bold",
    text: "B",
    isActive: (e) => e.isActive("bold"),
    run: (e) => e.chain().focus().toggleBold().run(),
  },
  {
    label: "Italic",
    text: "I",
    isActive: (e) => e.isActive("italic"),
    run: (e) => e.chain().focus().toggleItalic().run(),
  },
  {
    label: "Inline code",
    text: "</>",
    isActive: (e) => e.isActive("code"),
    run: (e) => e.chain().focus().toggleCode().run(),
  },
  {
    label: "Heading",
    text: "H",
    isActive: (e) => e.isActive("heading", { level: 2 }),
    run: (e) => e.chain().focus().toggleHeading({ level: 2 }).run(),
  },
  {
    label: "Bulleted list",
    text: "•",
    isActive: (e) => e.isActive("bulletList"),
    run: (e) => e.chain().focus().toggleBulletList().run(),
  },
  {
    label: "Numbered list",
    text: "1.",
    isActive: (e) => e.isActive("orderedList"),
    run: (e) => e.chain().focus().toggleOrderedList().run(),
  },
  {
    label: "Code block",
    text: "{ }",
    isActive: (e) => e.isActive("codeBlock"),
    run: (e) => e.chain().focus().toggleCodeBlock().run(),
  },
];

function Toolbar({ editor, label, disabled }: { editor: Editor; label: string; disabled: boolean }) {
  const active = useEditorState({ editor, selector: ({ editor: e }) => TOOLS.map((tool) => tool.isActive(e)) });
  return (
    <div role="toolbar" aria-label={`${label} formatting`} className="flex flex-wrap gap-1">
      {TOOLS.map((tool, index) => (
        <button
          key={tool.label}
          type="button"
          aria-label={tool.label}
          title={tool.label}
          aria-pressed={active[index]}
          disabled={disabled}
          className={TOOL}
          // Keep the editor's selection: the command acts on it, then focuses the editor again.
          onMouseDown={(event) => {
            event.preventDefault();
          }}
          onClick={() => {
            tool.run(editor);
          }}
        >
          {tool.text}
        </button>
      ))}
    </div>
  );
}

export type MarkdownEditorProps = {
  /** Names the editor for assistive technology and is shown above it. */
  label: string;
  /** The markdown to start from. It is kept exactly until someone edits it. */
  defaultValue: string;
  /** Called with the new markdown after every edit, never on load. */
  onChange?: (markdown: string) => void;
  /** Submits the markdown with a form under this name. */
  name?: string;
  maxLength?: number;
  disabled?: boolean;
};

/**
 * A lightweight WYSIWYG markdown editor that stores markdown. Headings, lists, code, links and
 * emphasis show formatted and are written back exactly; the Markdown view edits the text itself,
 * which is stored exactly as typed.
 */
export function MarkdownEditor({ label, defaultValue, onChange, name, maxLength, disabled = false }: MarkdownEditorProps) {
  const labelId = useId();
  const [value, setValue] = useState(defaultValue);
  const [source, setSource] = useState<string | null>(null);
  const trailing = useRef(trailingWhitespace(defaultValue));
  const [marked] = useState(createMarked);

  function change(markdown: string) {
    setValue(markdown);
    onChange?.(markdown);
  }

  const editor = useEditor({
    extensions: [
      // No trailing empty paragraph, no underline or strikethrough (not in the dialect), and
      // links are only made from markdown, never from typed URLs.
      StarterKit.configure({ trailingNode: false, underline: false, strike: false, link: { autolink: false, openOnClick: false } }),
      // TipTap types the option as the global `marked`; an instance is what it actually uses.
      Markdown.configure({ marked: marked as unknown as typeof defaultMarked }),
    ],
    content: defaultValue,
    contentType: "markdown",
    editable: !disabled,
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-multiline": "true",
        "aria-labelledby": labelId,
        class: `${FORMATTED} min-h-32 rounded border border-slate-300 bg-white px-3 py-2 focus:outline-2 focus:outline-slate-500`,
      },
    },
    onCreate: ({ editor: created }) => {
      writeTextExactly(created, marked);
    },
    onUpdate: ({ editor: updated }) => {
      change(updated.getMarkdown() + trailing.current);
    },
  });

  function toggleSource() {
    if (source === null) {
      setSource(editor.getMarkdown() + trailing.current);
      return;
    }
    trailing.current = trailingWhitespace(source);
    // Showing the edited text formatted is not itself an edit.
    editor.commands.setContent(source, { contentType: "markdown", emitUpdate: false });
    setSource(null);
  }

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span id={labelId} className="block text-sm font-medium">
          {label}
        </span>
        <button
          type="button"
          aria-pressed={source !== null}
          disabled={disabled}
          className={TOOL}
          onClick={toggleSource}
        >
          Markdown
        </button>
      </div>
      {source === null && <Toolbar editor={editor} label={label} disabled={disabled} />}
      <div hidden={source !== null}>
        <EditorContent editor={editor} />
      </div>
      {source !== null && (
        <textarea
          aria-label={`${label} (Markdown)`}
          rows={10}
          maxLength={maxLength}
          value={source}
          onChange={(event) => {
            setSource(event.target.value);
            change(event.target.value);
          }}
          className="block w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm"
        />
      )}
      {name !== undefined && <input type="hidden" name={name} value={value} />}
    </div>
  );
}
