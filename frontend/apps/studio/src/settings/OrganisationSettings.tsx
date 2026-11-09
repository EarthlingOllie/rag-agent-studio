import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type Session, useMe } from "../auth/session";
import { AuditPage } from "./AuditPage";
import { CredentialsPage } from "./CredentialsPage";
import { memberFailure, useLeaveOrganisation } from "./members";
import { MembersPage } from "./MembersPage";
import { ModelsPage } from "./ModelsPage";
import { RetentionWindow } from "./RetentionWindow";
import { ThemePage } from "./ThemePage";
import { useSetMfaPolicy } from "./mfaPolicy";

const TAB = "rounded px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 [&.active]:bg-slate-100 [&.active]:font-medium [&.active]:text-slate-900";

function useOrganisation() {
  const { organisationId } = useParams({ from: "/signed-in/organisations/$organisationId" });
  const session = useMe().data as Session;
  // OrganisationShell renders settings only for an Organisation the Member belongs to.
  const organisation = session.organisations.find((candidate) => candidate.id === organisationId) as Session["organisations"][number];
  return {
    organisationId,
    organisationName: organisation.name,
    memberId: session.member.id,
    isOwner: organisation.role === "owner",
    mfaRequired: organisation.mfa_required,
  };
}

const BUTTON = "rounded border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100 disabled:text-slate-600";

/** The Require MFA policy: Owners turn it on or off; everyone else sees which it is. */
function MfaPolicy({ organisationId, mfaRequired, isOwner }: { organisationId: string; mfaRequired: boolean; isOwner: boolean }) {
  const setPolicy = useSetMfaPolicy(organisationId);
  return (
    <section aria-labelledby="mfa-policy-heading" className="max-w-md space-y-3">
      <h2 id="mfa-policy-heading" className="text-lg font-semibold">
        Two-factor authentication
      </h2>
      <p className="text-sm text-slate-700">
        {mfaRequired
          ? "Every Member must use two-factor authentication. Members without it are asked to set it up before they can do anything else here."
          : "Members choose whether to use two-factor authentication."}
      </p>
      {isOwner ? (
        <>
          <FormError message={memberFailure(setPolicy.error)} />
          <button
            type="button"
            className={BUTTON}
            disabled={setPolicy.isPending}
            onClick={() => {
              setPolicy.mutate(!mfaRequired);
            }}
          >
            {setPolicy.isPending
              ? "Saving…"
              : mfaRequired
                ? "Stop requiring two-factor authentication"
                : "Require two-factor authentication"}
          </button>
        </>
      ) : (
        <p className="text-sm text-slate-700">Only Owners can change this.</p>
      )}
    </section>
  );
}

/** Any Member can leave; the last Owner is refused by the API and told why. */
function LeaveOrganisation({ organisationId, organisationName }: { organisationId: string; organisationName: string }) {
  const leave = useLeaveOrganisation(organisationId);
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  return (
    <section aria-labelledby="leave-heading" className="max-w-md space-y-3">
      <h2 id="leave-heading" className="text-lg font-semibold">
        Leave this Organisation
      </h2>
      <FormError message={memberFailure(leave.error)} />
      {confirming ? (
        <>
          <p className="text-sm text-slate-700">You will lose access to {organisationName} until someone invites you again.</p>
          <div className="flex gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={leave.isPending}
              onClick={() => {
                leave.mutate(undefined, {
                  onSuccess: () => {
                    void navigate({ to: "/" });
                  },
                  onError: () => {
                    setConfirming(false);
                  },
                });
              }}
            >
              Yes, leave {organisationName}
            </button>
            <button
              type="button"
              className={BUTTON}
              onClick={() => {
                setConfirming(false);
              }}
            >
              Cancel
            </button>
          </div>
        </>
      ) : (
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            leave.reset();
            setConfirming(true);
          }}
        >
          Leave {organisationName}
        </button>
      )}
    </section>
  );
}

/**
 * Organisation settings, with a tab per area. Every Member sees General, Credentials, Models and Theme
 * (Editors view the Theme without editing it); the Members and Audit tabs are shown to Owners only.
 */
export function OrganisationSettingsLayout() {
  const { organisationId, isOwner } = useOrganisation();
  return (
    <section aria-labelledby="page-heading">
      <h1 id="page-heading" className="text-2xl font-semibold">
        Organisation settings
      </h1>
      <nav aria-label="Organisation settings" className="mt-4 flex gap-2 border-b border-slate-200 pb-2">
        <Link to="/organisations/$organisationId/settings" params={{ organisationId }} activeOptions={{ exact: true }} className={TAB}>
          General
        </Link>
        <Link to="/organisations/$organisationId/settings/credentials" params={{ organisationId }} className={TAB}>
          Credentials
        </Link>
        <Link to="/organisations/$organisationId/settings/models" params={{ organisationId }} className={TAB}>
          Models
        </Link>
        <Link to="/organisations/$organisationId/settings/theme" params={{ organisationId }} className={TAB}>
          Theme
        </Link>
        {isOwner && (
          <>
            <Link to="/organisations/$organisationId/settings/members" params={{ organisationId }} className={TAB}>
              Members
            </Link>
            <Link to="/organisations/$organisationId/settings/audit" params={{ organisationId }} className={TAB}>
              Audit
            </Link>
          </>
        )}
      </nav>
      <div className="mt-6">
        <Outlet />
      </div>
    </section>
  );
}

export function GeneralSettingsPage() {
  const { organisationId, organisationName, isOwner, mfaRequired } = useOrganisation();
  return (
    <div className="space-y-8">
      <MfaPolicy key={`mfa-${organisationId}`} organisationId={organisationId} mfaRequired={mfaRequired} isOwner={isOwner} />
      <RetentionWindow key={`retention-${organisationId}`} organisationId={organisationId} isOwner={isOwner} />
      <LeaveOrganisation key={organisationId} organisationId={organisationId} organisationName={organisationName} />
    </div>
  );
}

export function AuditSettingsPage() {
  const { organisationId, isOwner } = useOrganisation();
  return <AuditPage organisationId={organisationId} isOwner={isOwner} />;
}

export function MembersSettingsPage() {
  const { organisationId, memberId, isOwner } = useOrganisation();
  return <MembersPage organisationId={organisationId} memberId={memberId} isOwner={isOwner} />;
}

export function CredentialsSettingsPage() {
  const { organisationId, isOwner } = useOrganisation();
  return <CredentialsPage organisationId={organisationId} isOwner={isOwner} />;
}

export function ThemeSettingsPage() {
  const { organisationId, isOwner } = useOrganisation();
  return <ThemePage organisationId={organisationId} isOwner={isOwner} />;
}

export function ModelsSettingsPage() {
  const { organisationId, isOwner } = useOrganisation();
  return <ModelsPage organisationId={organisationId} isOwner={isOwner} />;
}
