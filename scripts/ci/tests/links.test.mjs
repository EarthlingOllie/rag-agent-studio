// The link check (`make link-check`): every relative link in the repository's Markdown resolves.
// Run with Node's coverage thresholds by `make link-check`.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

import { checkLinks, gitMarkdownFiles, main, slugify } from "../links.mjs";

function repo(files) {
  const root = mkdtempSync(join(tmpdir(), "links-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  return root;
}

const problems = (root, files) => checkLinks(root, files).map((p) => `${p.file}:${p.line} ${p.target} (${p.reason})`);

test("links to files and folders that exist pass, relative to the linking file or to the root", () => {
  const root = repo({
    "README.md": "See [the plan](docs/plan.md), the [ADRs](docs/adr/), ![a picture](docs/shot.png \"Shot\") and [up](<docs/a b.md>).\n",
    "docs/plan.md": "Back to the [README](../README.md) or [from the root](/README.md) or [encoded](a%20b.md).\n",
    "docs/a b.md": "x\n",
    "docs/shot.png": "",
    "docs/adr/0001.md": "",
  });
  assert.deepEqual(problems(root, ["README.md", "docs/plan.md"]), []);
});

test("a link to a missing file is reported with its file and line", () => {
  const root = repo({ "README.md": "# Title\n\nSee [gone](docs/gone.md) and [also](./nope/).\n" });
  assert.deepEqual(problems(root, ["README.md"]), [
    "README.md:3 docs/gone.md (no such file or folder)",
    "README.md:3 ./nope/ (no such file or folder)",
  ]);
});

test("external links, mail links and links in code are not checked", () => {
  const root = repo({
    "README.md": [
      "[web](https://example.com/x) [mail](mailto:a@b.example) [proto](//cdn.example/x)",
      "`[inline](missing-inline.md)`",
      "```md",
      "[fenced](missing-fenced.md)",
      "```",
      "~~~",
      "[tilde](missing-tilde.md)",
      "~~~",
      "",
    ].join("\n"),
  });
  assert.deepEqual(problems(root, ["README.md"]), []);
});

test("reference-style link definitions are checked; footnotes are not links", () => {
  const root = repo({ "README.md": "[the plan][plan][^1]\n\n[plan]: docs/plan.md\n[web]: https://example.com\n[^1]: Note for readers.\n" });
  assert.deepEqual(problems(root, ["README.md"]), ["README.md:3 docs/plan.md (no such file or folder)"]);
});

test("anchors must name a heading in the target Markdown file, or in the same file", () => {
  const root = repo({
    "README.md": [
      "# Rag Agent Studio",
      "## Five-minute demo",
      "## Testing: 100% coverage, `seams` & [evals](docs/x.md)",
      "## Five-minute demo",
      '<a id="custom-anchor"></a>',
      "[ok](#five-minute-demo) [dup](#five-minute-demo-1) [code](#testing-100-coverage-seams--evals) [html](#custom-anchor)",
      "[bad](#nowhere) [other](docs/x.md#heading-two) [missing](docs/x.md#nope) [png](docs/x.png#frag)",
      "",
    ].join("\n"),
    "docs/x.md": "# Heading one\n## Heading **two**\n",
    "docs/x.png": "",
  });
  assert.deepEqual(problems(root, ["README.md"]), [
    "README.md:7 #nowhere (no heading or anchor named nowhere)",
    "README.md:7 docs/x.md#nope (no heading or anchor named nope)",
  ]);
});

test("slugs follow GitHub's rules", () => {
  assert.equal(slugify("Deploy and destroy (with cost)"), "deploy-and-destroy-with-cost");
  assert.equal(slugify("Ünïcode Title_with_underscores"), "ünïcode-title_with_underscores");
});

test("the files come from git: tracked Markdown only", () => {
  const root = repo({ "README.md": "", "docs/a.md": "", "notes.txt": "", "untracked.md": "" });
  execFileSync("git", ["init", "-q"], { cwd: root });
  execFileSync("git", ["add", "README.md", "docs/a.md", "notes.txt"], { cwd: root });
  assert.deepEqual(gitMarkdownFiles(root), ["README.md", "docs/a.md"]);
});

test("main prints each broken link and fails, or says how many links it checked", () => {
  const out = [];
  const io = { log: (line) => out.push(`log: ${line}`), error: (line) => out.push(`error: ${line}`) };
  const good = repo({ "README.md": "[a](b.md) [b](b.md#b)\n", "b.md": "# B\n" });
  assert.equal(main(good, ["README.md", "b.md"], io), 0);
  const bad = repo({ "README.md": "[a](missing.md)\n" });
  assert.equal(main(bad, ["README.md"], io), 1);
  assert.deepEqual(out, [
    "log: Checked 2 relative links in 2 Markdown files: all resolve.",
    "error: README.md:1 missing.md (no such file or folder)",
    "error: 1 broken relative link in 1 Markdown file.",
  ]);
});
