// `pnpm palette-ratchet [--write]`, from frontend/. See ratchet.mjs.
import { main } from "./ratchet.mjs";

process.exitCode = main(process.argv.slice(2));
