import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { adaSession } from "./auth";
import { server } from "./server";

export const GOOD_CODE = "123456";
export const QR_CODE = "data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%2F%3E";
export const SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";
export const PASSWORD = "correct horse battery";

export function recoveryCodes(prefix: string): string[] {
  return Array.from({ length: 10 }, (_, index) => `${prefix}AA-BBBB-CCCC-DD${String.fromCharCode(65 + index)}A`);
}

const incorrect = (detail: string) => HttpResponse.json({ detail }, { status: 400 });

/**
 * A stateful stand-in for the MFA API: enrolment turns MFA on with `GOOD_CODE`, recovery codes
 * count down, and disabling needs `PASSWORD` and `GOOD_CODE`. Returns the requests it received.
 */
export function fakeMfaApi(options: { enabled?: boolean; remaining?: number } = {}) {
  let status: Schemas["MfaStatusResponse"] = {
    enabled: options.enabled ?? false,
    recovery_codes_remaining: options.remaining ?? (options.enabled ? 10 : 0),
  };
  let batch = 0;
  const requests: { route: string; body: unknown }[] = [];

  server.use(
    http.get("*/api/auth/mfa", () => HttpResponse.json(status)),
    http.post("*/api/auth/mfa/enrolment", () => {
      requests.push({ route: "enrolment", body: null });
      return HttpResponse.json(
        { secret: SECRET, otpauth_uri: `otpauth://totp/x?secret=${SECRET}`, qr_code: QR_CODE },
        { status: 201 },
      );
    }),
    http.post("*/api/auth/mfa/enrolment/confirm", async ({ request }) => {
      const body = (await request.json()) as { code: string };
      requests.push({ route: "confirm", body });
      if (body.code !== GOOD_CODE) return incorrect("Code is incorrect");
      status = { enabled: true, recovery_codes_remaining: 10 };
      return HttpResponse.json({ recovery_codes: recoveryCodes("A") });
    }),
    http.post("*/api/auth/mfa/recovery-codes", async ({ request }) => {
      const body = (await request.json()) as { code: string };
      requests.push({ route: "recovery-codes", body });
      if (body.code !== GOOD_CODE) return incorrect("Code is incorrect");
      batch += 1;
      status = { enabled: true, recovery_codes_remaining: 10 };
      return HttpResponse.json({ recovery_codes: recoveryCodes(String.fromCharCode(66 + batch)) });
    }),
    http.post("*/api/auth/mfa/disable", async ({ request }) => {
      const body = (await request.json()) as { password: string; code: string };
      requests.push({ route: "disable", body });
      if (body.code !== GOOD_CODE || body.password !== PASSWORD) return incorrect("Password or code is incorrect");
      status = { enabled: false, recovery_codes_remaining: 0 };
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { requests };
}

/** Sign-in for a Member with MFA: the password step answers 202, and `GOOD_CODE` finishes it. */
export function fakeMfaSignIn() {
  let signedIn = false;
  const requests: { route: string; body: unknown }[] = [];
  server.use(
    http.get("*/api/auth/me", () =>
      signedIn ? HttpResponse.json(adaSession) : HttpResponse.json({ detail: "Not signed in" }, { status: 401 }),
    ),
    http.post("*/api/auth/sign-in", async ({ request }) => {
      requests.push({ route: "sign-in", body: await request.json() });
      return HttpResponse.json({ mfa_required: true }, { status: 202 });
    }),
    http.post("*/api/auth/mfa/verify", async ({ request }) => {
      const body = (await request.json()) as { code: string };
      requests.push({ route: "verify", body });
      if (body.code !== GOOD_CODE && body.code !== "AAAA-BBBB-CCCC-DDDD") return incorrect("Code is incorrect");
      signedIn = true;
      return HttpResponse.json(adaSession);
    }),
  );
  return { requests };
}
