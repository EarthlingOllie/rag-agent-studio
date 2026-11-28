// Runs the rehearsal's front end (front.mjs): FRONT_PORT (default 4566), FRONT_HOST (default all addresses) and
// FLOCI_URL (default http://floci:4566, Floci on the rehearsal's network).
import { startFront } from "./front.mjs";

const server = await startFront({
  port: Number(process.env.FRONT_PORT ?? 4566),
  host: process.env.FRONT_HOST ?? "0.0.0.0",
  upstream: process.env.FLOCI_URL ?? "http://floci:4566",
});
console.log(`The rehearsal's front end listens on :${server.address().port}`);
