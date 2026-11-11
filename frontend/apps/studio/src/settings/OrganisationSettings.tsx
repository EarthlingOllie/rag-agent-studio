import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type Session, useMe } from "../auth/session";
import { button, ConfirmDialog, layout, PageHeader, surface, TabRow, tabLink, text, ToastProvider } from "../design";
import { useSettingsAreas } from "../shell/settingsNavigation";
import { AuditPage } from "./AuditPage";
import { CredentialsPage } from "./CredentialsPage";
import { memberFailure, useLeaveOrganisation } from "./members";
import { MembersPage } from "./MembersPage";
import { ModelsPage } from "./ModelsPage";
import { RetentionWindow } from "./RetentionWindow";
import { ThemePage } from "./ThemePage";
import { useSetMfaPolicy } from "./mfaPolicy";

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

/** The Require MFA policy: Owners turn it on or off; everyone else sees which it is. */
function MfaPolicy({ organisationId, mfaRequired, isOwner }: { organisationId: string; mfaRequired: boolean; isOwner: boolean }) {
  const setPolicy = useSetMfaPolicy(organisationId);
  return (
    <section aria-labelledby="mfa-policy-heading" className={`${surface.panel} space-y-3`}>
      <h2 id="mfa-policy-heading" className={text.heading}>
        Two-factor authentication
      </h2>
      <p className={text.muted}>
        {mfaRequired
          ? "Every Member must use two-factor authentication. Members without it are asked to set it up before they can do anything else here."
          : "Members choose whether to use two-factor authentication."}
      </p>
      {isOwner ? (
        <>
          <FormError message={memberFailure(setPolicy.error)} />
          <button
            type="button"
            className={button.secondary}
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
        <p className={text.muted}>Only Owners can change this.</p>
      )}
    </section>
  );
}

/** Any Member can leave, after confirming; the last Owner is refused by the API and told why. */
function LeaveOrganisation({ organisationId, organisationName }: { organisationId: string; organisationName: string }) {
  const leave = useLeaveOrganisation(organisationId);
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  return (
    <section aria-labelledby="leave-heading" className={`${surface.panel} space-y-3`}>
      <h2 id="leave-heading" className={text.heading}>
        Leave this Organisation
      </h2>
      <FormError message={memberFailure(leave.error)} />
      <button
        type="button"
        className={button.danger}
        onClick={() => {
          leave.reset();
          setConfirming(true);
        }}
      >
        Leave {organisationName}
      </button>
      <ConfirmDialog
        open={confirming}
        title={`Leave ${organisationName}?`}
        confirmLabel={`Yes, leave ${organisationName}`}
        destructive
        busy={leave.isPending}
        onCancel={() => {
          setConfirming(false);
        }}
        onConfirm={() => {
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
        You will lose access to {organisationName} until someone invites you again.
      </ConfirmDialog>
    </section>
  );
}

/** Organisation settings' areas as tabs under its header; Members and Audit are left out for anyone but an Owner. */
function SettingsTabs({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const areas = useSettingsAreas(organisationId).filter((area) => area.ownersOnly !== true || isOwner);
  return (
    <TabRow label="Organisation settings">
      {areas.map((area) => (
        <li key={area.label} className="flex">
          <Link
            to={area.to}
            params={{ organisationId }}
            // The router would mark General current on every area; only our own marking counts.
            activeOptions={{ exact: true, includeSearch: false }}
            aria-current={area.current ? "page" : undefined}
            className={tabLink}
          >
            {area.label}
          </Link>
        </li>
      ))}
    </TabRow>
  );
}

/**
 * Organisation settings. The area (General, Credentials, Models, Theme, and Members and Audit for
 * Owners) is chosen from the tab row under the header; Editors view the Theme without editing it.
 * Changes here confirm with a toast.
 */
export function OrganisationSettingsLayout() {
  const { organisationId, organisationName, isOwner } = useOrganisation();
  return (
    <ToastProvider>
      <div className={layout.stack}>
        <PageHeader title="Organisation settings" description={`How ${organisationName} works for every Project and Member.`} />
        <SettingsTabs organisationId={organisationId} isOwner={isOwner} />
        <Outlet />
      </div>
    </ToastProvider>
  );
}

export function GeneralSettingsPage() {
  const { organisationId, organisationName, isOwner, mfaRequired } = useOrganisation();
  return (
    <div className="grid max-w-2xl gap-6">
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
  const { organisationId, organisationName, memberId, isOwner } = useOrganisation();
  return <MembersPage organisationId={organisationId} organisationName={organisationName} memberId={memberId} isOwner={isOwner} />;
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
