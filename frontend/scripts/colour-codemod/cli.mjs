import { main } from "./codemod.mjs";

process.exitCode = main(process.argv.slice(2));
