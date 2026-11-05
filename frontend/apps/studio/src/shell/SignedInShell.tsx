import { Link, Navigate, Outlet, useNavigate, useParams } from "@tanstack/react-router";

import { type Session, useMe, useSignOut } from "../auth/session";
import { OrganisationSwitcher } from "./OrganisationSwitcher";

function Centered({ children, role }: { children: string; role: "status" | "alert" }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-900">
      <p role={role}>{children}</p>
    </main>
  );
}

/** Everything a signed-in Member sees. Signed-out visitors are sent to the sign-in screen. */
export function SignedInShell() {
  const me = useMe();
  if (me.isPending) return <Centered role="status">Loading…</Centered>;
  if (me.isError) return <Centered role="alert">The Studio could not reach the API. Try again shortly.</Centered>;
  if (me.data === null) return <Navigate to="/sign-in" />;
  return <Outlet />;
}

/** `/`: opens the active Organisation: the one the Member last switched to, or their first. */
export function HomeRedirect() {
  const { data } = useMe();
  const active = (data as Session).active_organisation_id;
  if (active === null) {
    return <Centered role="status">You don't belong to any Organisation yet.</Centered>;
  }
  return <Navigate to="/organisations/$organisationId/projects" params={{ organisationId: active }} />;
}

function SignOutButton() {
  const signOut = useSignOut();
  const navigate = useNavigate();
  return (
    <div className="flex items-center gap-3">
      {signOut.isError && (
        <p role="alert" className="text-sm text-red-800">
          Sign-out failed. Try again.
        </p>
      )}
      <button
        type="button"
        disabled={signOut.isPending}
        onClick={() => {
          signOut.mutate(undefined, {
            onSuccess: () => {
              void navigate({ to: "/sign-in" });
            },
          });
        }}
        className="rounded border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100"
      >
        Sign out
      </button>
    </div>
  );
}

const NAV_LINK = "rounded px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 [&.active]:bg-slate-100 [&.active]:font-medium [&.active]:text-slate-900";

/** The Studio frame for one Organisation: navigation, the Member, and the page. */
export function OrganisationShell() {
  const { data } = useMe();
  const session = data as Session;
  const { organisationId } = useParams({ from: "/signed-in/organisations/$organisationId" });
  const organisation = session.organisations.find((candidate) => candidate.id === organisationId);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-6 px-6 py-3">
          <div className="flex items-center gap-6">
            <span className="font-semibold">RAG Agent Studio</span>
            <OrganisationSwitcher session={session} organisationId={organisationId} />
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-700">{session.member.name}</span>
            {organisation && (
              <Link
                to="/organisations/$organisationId/profile"
                params={{ organisationId }}
                className="text-sm text-slate-700 underline"
              >
                Profile
              </Link>
            )}
            <SignOutButton />
          </div>
        </div>
      </header>
      {organisation ? (
        <div className="mx-auto flex max-w-5xl gap-8 px-6 py-8">
          <nav aria-label="Organisation" className="flex w-48 shrink-0 flex-col gap-1">
            <Link to="/organisations/$organisationId/projects" params={{ organisationId }} className={NAV_LINK}>
              Projects
            </Link>
            <Link to="/organisations/$organisationId/settings" params={{ organisationId }} className={NAV_LINK}>
              Organisation settings
            </Link>
            <Link to="/organisations/$organisationId/security" params={{ organisationId }} className={NAV_LINK}>
              Security
            </Link>
          </nav>
          <main className="min-w-0 flex-1">
            <Outlet />
          </main>
        </div>
      ) : (
        <main className="mx-auto max-w-5xl px-6 py-8">
          <h1 className="text-2xl font-semibold">Organisation not found</h1>
          <p className="mt-2 text-slate-700">
            It doesn't exist, or you are not a Member of it. <Link to="/" className="underline">Go to your Organisation</Link>
          </p>
        </main>
      )}
    </div>
  );
}
