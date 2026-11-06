// Screenshots of the Theme tab's logo and avatar from the running stack. Run from frontend/ of the clone:
//   node <evidence>/shots.mjs <out dir>     (BASE defaults to this ticket's Studio port)
import { chromium } from "@playwright/test";
import { deflateSync } from "node:zlib";

const BASE = process.env.BASE ?? "http://localhost:45206";
const OUT = process.argv[2];
const id = Math.random().toString(16).slice(2, 10);
const owner = { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: `correct horse ${id}`, organisation_name: "Analytical Engines" };

// A solid-colour 64x64 PNG, built here so the script needs no image files.
function png([r, g, b], size = 64) {
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (buf) => { let c = 0xffffffff; for (const x of buf) c = crcTable[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(size * 3).map((_, i) => [r, g, b][i % 3])]);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(Buffer.concat(Array(size).fill(row)))), chunk("IEND", Buffer.alloc(0))]);
}

const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
const context = await browser.newContext({ baseURL: BASE, viewport: { width: 1400, height: 1700 } });
const page = await context.newPage();
await page.request.post("/api/auth/sign-up", { data: owner });
const me = await (await page.request.get("/api/auth/me")).json();
const org = me.organisations[0].id;
const shot = (p, name) => p.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
const images = () => page.getByRole("region", { name: "Logo and avatar" });

await page.goto(`/organisations/${org}/settings/theme`);
await images().getByText("No logo yet.").waitFor();
await shot(page, "studio-theme-no-images");

await images().getByLabel("Upload logo").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: png([185, 28, 28]) });
await images().getByText("Logo saved. The widget uses it now.").waitFor();
await images().getByLabel("Upload avatar").setInputFiles({ name: "avatar.png", mimeType: "image/png", buffer: png([13, 148, 136]) });
await images().getByText("Avatar saved. The widget uses it now.").waitFor();
await page.waitForTimeout(500);
await shot(page, "studio-theme-logo-and-avatar-in-preview");

await images().getByLabel("Replace logo").setInputFiles({ name: "logo.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg xmlns='http://www.w3.org/2000/svg'/>") });
await images().getByRole("alert").waitFor();
await shot(page, "studio-theme-image-type-refused");

await images().getByLabel("Replace logo").setInputFiles({ name: "logo-2.png", mimeType: "image/png", buffer: png([79, 70, 229]) });
await images().getByText("Logo saved. The widget uses it now.").waitFor();
await images().getByRole("button", { name: "Remove avatar" }).click();
await images().getByText("No avatar yet.").waitFor();
await page.waitForTimeout(500);
await shot(page, "studio-theme-logo-replaced-avatar-removed");

await page.goto(`/organisations/${org}/settings/audit`);
await page.getByRole("cell", { name: "theme.updated" }).first().waitFor();
await shot(page, "studio-audit-theme-image-events");

const invite = await (await page.request.post(`/api/organisations/${org}/invites`, { data: { email: `grace-${id}@example.test`, role: "editor", send_email: false } })).json();
const token = new URL(invite.link).searchParams.get("token");
const editor = await (await browser.newContext({ baseURL: BASE, viewport: { width: 1400, height: 1700 } })).newPage();
await editor.request.post("/api/invites/sign-up", { data: { token, name: "Grace Hopper", password: `correct horse ${id}` } });
await editor.goto(`/organisations/${org}/settings/theme`);
await editor.getByText("Only Owners can change the Theme.").waitFor();
await editor.waitForTimeout(500);
await shot(editor, "studio-theme-images-editor-read-only");
await browser.close();
