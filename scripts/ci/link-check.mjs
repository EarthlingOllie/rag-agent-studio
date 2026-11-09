#!/usr/bin/env node
// `make link-check`: fails when a relative link in any Markdown file git tracks doesn't resolve.
import { gitMarkdownFiles, main } from "./links.mjs";

const root = process.cwd();
process.exitCode = main(root, gitMarkdownFiles(root), { log: console.log, error: console.error });
