import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, field, surface, table, text, useToast } from "../design";
import {
  type Invite,
  InviteRequestError,
  type IssuedInvite,
  ROLE_NAMES,
  type Role,
  useCreateInvite,
  usePendingInvites,
  useRenewInvite,
  useRevokeInvite,
} from "../invites/invites";
import { MembersList } from "./MembersList";

function failure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof InviteRequestError) {
    if (error.status === 409 && error.detail) return error.detail;
    if (error.status === 422) return "Enter a valid email address.";
  }
  return "Something went wrong. Try again.";
}

/** `2026-06-01T09:30:00Z` → `2026-06-01`, the same for every viewer. */
function day(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

function issuedMessage(issued: IssuedInvite, emailRequested: boolean): string {
  const { email } = issued.invite;
  if (issued.email_sent) return `We emailed an invite to ${email}. You can also copy the link and send it yourself.`;
  if (emailRequested) return `The email to ${email} couldn't be sent. Copy the link and send it yourself.`;
  return `Copy the link and send it to ${email}.`;
}

/** The link an Owner can copy for a just-issued invite. The toast has confirmed the invite. */
function InviteLink({ issued, emailRequested }: { issued: IssuedInvite; emailRequested: boolean }) {
  const [copied, setCopied] = useState<"yes" | "failed" | "no">("no");
  return (
    <section aria-label="New invite" className={`${surface.panel} flex flex-col gap-2 text-sm text-ink-2`}>
      <p>{issuedMessage(issued, emailRequested)}</p>
      <label className={field.label} htmlFor="invite-link">
        Invite link for {issued.invite.email}
      </label>
      <div className="flex gap-2">
        <input id="invite-link" readOnly value={issued.link} className={`${field.inputMono} mt-0 text-xs`} />
        <button
          type="button"
          className={button.secondary}
          onClick={() => {
            navigator.clipboard.writeText(issued.link).then(
              () => {
                setCopied("yes");
              },
              () => {
                setCopied("failed");
              },
            );
          }}
        >
          Copy link
        </button>
      </div>
      {copied === "yes" && <p>Link copied.</p>}
      {copied === "failed" && <p className="text-danger">Couldn't copy. Select the link and copy it yourself.</p>}
      <p className={text.muted}>The link works once and expires on {day(issued.invite.expires_at)}.</p>
    </section>
  );
}

function InviteForm({ organisationId, onIssued }: { organisationId: string; onIssued: (issued: IssuedInvite, emailed: boolean) => void }) {
  const createInvite = useCreateInvite(organisationId);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const sendEmail = data.get("send_email") === "on";
    createInvite.mutate(
      { email: data.get("email") as string, role: data.get("role") as Role, send_email: sendEmail },
      {
        onSuccess: (issued) => {
          form.reset();
          onIssued(issued, sendEmail);
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} aria-label="Invite someone" className={`${surface.panel} flex flex-col gap-4`}>
      <h2 className={text.heading}>Invite someone</h2>
      <FormError message={failure(createInvite.error)} />
      <div>
        <label htmlFor="invite-email" className={field.label}>
          Email
        </label>
        <input id="invite-email" name="email" type="email" required autoComplete="off" className={field.input} />
      </div>
      <div>
        <label htmlFor="invite-role" className={field.label}>
          Role
        </label>
        <select id="invite-role" name="role" defaultValue="editor" className={field.select}>
          <option value="editor">Editor</option>
          <option value="owner">Owner</option>
        </select>
      </div>
      <label className="flex items-center gap-2 text-sm text-ink-2">
        <input type="checkbox" name="send_email" defaultChecked className={field.checkbox} />
        Email the invite link
      </label>
      <button type="submit" disabled={createInvite.isPending} className={`${button.primary} self-start`}>
        {createInvite.isPending ? "Inviting…" : "Invite"}
      </button>
    </form>
  );
}

function PendingRow({
  invite,
  organisationId,
  onIssued,
}: {
  invite: Invite;
  organisationId: string;
  onIssued: (issued: IssuedInvite) => void;
}) {
  const renew = useRenewInvite(organisationId);
  const revoke = useRevokeInvite(organisationId);
  const toast = useToast();
  const busy = renew.isPending || revoke.isPending;
  return (
    <tr className={table.row}>
      <td className={`${table.td} font-medium`}>{invite.email}</td>
      <td className={table.td}>{ROLE_NAMES[invite.role]}</td>
      <td className={table.tdMuted}>{invite.invited_by.name}</td>
      <td className={invite.expired ? table.tdMuted : `${table.td} font-mono text-[13px]`}>
        {invite.expired ? "Expired" : day(invite.expires_at)}
      </td>
      <td className={table.td}>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className={button.secondary}
            disabled={busy}
            aria-label={`New link for ${invite.email}`}
            onClick={() => {
              renew.mutate(invite.id, {
                onSuccess: (issued) => {
                  toast.show(`New invite link for ${invite.email}.`);
                  onIssued(issued);
                },
              });
            }}
          >
            New link
          </button>
          <button
            type="button"
            className={button.danger}
            disabled={busy}
            aria-label={`Revoke invite for ${invite.email}`}
            onClick={() => {
              revoke.mutate(invite.id, {
                onSuccess: () => {
                  toast.show(`Revoked the invite for ${invite.email}.`);
                },
              });
            }}
          >
            Revoke
          </button>
        </div>
        {(renew.isError || revoke.isError) && (
          <p role="alert" className={field.error}>
            That didn't work. The invite may have been accepted or revoked already.
          </p>
        )}
      </td>
    </tr>
  );
}

function PendingInvites({ organisationId, onIssued }: { organisationId: string; onIssued: (issued: IssuedInvite) => void }) {
  const invites = usePendingInvites(organisationId);
  if (invites.isPending) return <p role="status" className={text.muted}>Loading invites…</p>;
  if (invites.isError) return <p role="alert" className={text.muted}>The pending invites could not be loaded. Try again shortly.</p>;
  if (invites.data.length === 0) return <p className={text.muted}>No pending invites.</p>;
  return (
    <div className={table.wrap}>
      <table className={table.table} aria-label="Pending invites">
        <thead>
          <tr>
            <th className={table.th}>Email</th>
            <th className={table.th}>Role</th>
            <th className={table.th}>Invited by</th>
            <th className={table.th}>Expires</th>
            <th className={table.th}>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {invites.data.map((invite) => (
            <PendingRow key={invite.id} invite={invite} organisationId={organisationId} onIssued={onIssued} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Members: Owners see and manage Members, invite people and manage pending invites. Invites and
 * member changes are confirmed by a toast; a new invite's link stays on the page to copy.
 */
export function MembersPage({
  organisationId,
  organisationName,
  memberId,
  isOwner,
}: {
  organisationId: string;
  organisationName: string;
  memberId: string;
  isOwner: boolean;
}) {
  const [issued, setIssued] = useState<{ invite: IssuedInvite; emailed: boolean } | null>(null);
  const toast = useToast();
  if (!isOwner) return <p className={text.muted}>Only Owners can manage Members and invites.</p>;
  return (
    <section aria-labelledby="members-heading" className="flex flex-col gap-7">
      <div className="flex flex-col gap-3">
        <h2 id="members-heading" className={text.heading}>
          Members
        </h2>
        <MembersList organisationId={organisationId} organisationName={organisationName} memberId={memberId} />
      </div>
      <div className="grid max-w-2xl gap-4">
        <InviteForm
          organisationId={organisationId}
          onIssued={(invite, emailed) => {
            toast.show(`Invited ${invite.invite.email}.`);
            setIssued({ invite, emailed });
          }}
        />
        {issued && <InviteLink key={issued.invite.link} issued={issued.invite} emailRequested={issued.emailed} />}
      </div>
      <div className="flex flex-col gap-3">
        <h2 className={text.heading}>Pending invites</h2>
        <PendingInvites
          organisationId={organisationId}
          onIssued={(invite) => {
            setIssued({ invite, emailed: false });
          }}
        />
      </div>
    </section>
  );
}
