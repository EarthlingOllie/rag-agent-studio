// Checks that every relative link in the repository's Markdown resolves: the file or folder exists,
// and an anchor (`#…`) names a heading or an explicit anchor in the target Markdown file.
// External links (any URL scheme, or `//host`) are not checked: the check runs offline.
// The command line is `link-check.mjs`; `make link-check` runs both with the tests.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, posix } from "node:path";

const EXTERNAL = /^([a-z][a-z0-9+.-]*:|\/\/)/i;
const FENCE = /^\s{0,3}(```|~~~)/;
// [text](target "title"), ![alt](<target>): the target, without the optional title.
const INLINE = /!?\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+"[^"]*")?\s*\)/g;
// [label]: target (not a footnote, [^1]: text)
const DEFINITION = /^\s{0,3}\[(?!\^)[^\]]+\]:\s*(<[^>]*>|\S+)/;
const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/;
const HTML_ANCHOR = /<a\s+(?:id|name)="([^"]+)"/g;

/** GitHub's heading anchor: lower case, punctuation dropped, spaces to hyphens. */
export function slugify(heading) {
  return heading
    .toLowerCase()
    .replace(/[^\p{L}\p{M}\p{N}\p{Pc} -]/gu, "")
    .replace(/ /g, "-");
}

/** A heading's text as rendered: links reduced to their text, code and emphasis marks dropped. */
function headingText(markdown) {
  return markdown.replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[`*]/g, "");
}

/** Each line of `markdown` outside fenced code, as is and with inline code blanked, and its line number. */
function proseLines(markdown) {
  const lines = [];
  let fenced = false;
  markdown.split("\n").forEach((line, index) => {
    if (FENCE.test(line)) {
      fenced = !fenced;
    } else if (!fenced) {
      lines.push({ raw: line, text: line.replace(/`[^`]*`/g, ""), line: index + 1 });
    }
  });
  return lines;
}

function anchorsOf(markdown) {
  const anchors = new Set();
  const seen = new Map();
  for (const { raw, text } of proseLines(markdown)) {
    const heading = HEADING.exec(raw);
    if (heading) {
      const slug = slugify(headingText(heading[1]));
      const count = seen.get(slug) ?? 0;
      seen.set(slug, count + 1);
      anchors.add(count === 0 ? slug : `${slug}-${String(count)}`);
    }
    for (const match of text.matchAll(HTML_ANCHOR)) anchors.add(match[1]);
  }
  return anchors;
}

function linksOf(markdown) {
  const links = [];
  for (const { text, line } of proseLines(markdown)) {
    for (const match of text.matchAll(INLINE)) links.push({ target: match[1], line });
    const definition = DEFINITION.exec(text);
    if (definition) links.push({ target: definition[1], line });
  }
  return links.map(({ target, line }) => ({ target: target.replace(/^<(.*)>$/, "$1"), line }));
}

function scan(root, files) {
  const problems = [];
  let checked = 0;
  const anchorsIn = (file) => anchorsOf(readFileSync(join(root, file), "utf8"));
  for (const file of files) {
    for (const { target, line } of linksOf(readFileSync(join(root, file), "utf8"))) {
      if (EXTERNAL.test(target)) continue;
      checked += 1;
      const [pathPart, anchor] = target.split("#", 2);
      const path = decodeURIComponent(pathPart);
      let resolved = file;
      if (path !== "") {
        resolved = path.startsWith("/") ? path.slice(1) : posix.join(dirname(file), path);
      }
      if (!existsSync(join(root, resolved))) {
        problems.push({ file, line, target, reason: "no such file or folder" });
      } else if (anchor !== undefined && resolved.endsWith(".md") && !anchorsIn(resolved).has(anchor)) {
        problems.push({ file, line, target, reason: `no heading or anchor named ${anchor}` });
      }
    }
  }
  return { checked, problems };
}

/** Every broken relative link in `files` (paths relative to `root`), with its file and line. */
export function checkLinks(root, files) {
  return scan(root, files).problems;
}

/** The Markdown files git tracks under `root`. */
export function gitMarkdownFiles(root) {
  return execFileSync("git", ["ls-files", "-z", "--", "*.md"], { cwd: root, encoding: "utf8" })
    .split("\0")
    .filter((file) => file !== "");
}

const plural = (count, word) => `${String(count)} ${word}${count === 1 ? "" : "s"}`;

/** Prints each broken link; returns the exit code. */
export function main(root, files, io) {
  const { checked, problems } = scan(root, files);
  if (problems.length === 0) {
    io.log(`Checked ${plural(checked, "relative link")} in ${plural(files.length, "Markdown file")}: all resolve.`);
    return 0;
  }
  for (const p of problems) io.error(`${p.file}:${String(p.line)} ${p.target} (${p.reason})`);
  const broken = new Set(problems.map((p) => p.file)).size;
  io.error(`${plural(problems.length, "broken relative link")} in ${plural(broken, "Markdown file")}.`);
  return 1;
}
