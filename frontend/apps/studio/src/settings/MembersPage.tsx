import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
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

const INPUT = "mt-1 block w-full rounded border border-slate-400 bg-white px-3 py-2 focus:outline-2 focus:outline-slate-900";
const BUTTON = "rounded border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100 disabled:text-slate-600";

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

/** The link an Owner can copy for a just-issued invite. */
function InviteLink({ issued, emailRequested }: { issued: IssuedInvite; emailRequested: boolean }) {
  const [copied, setCopied] = useState<"yes" | "failed" | "no">("no");
  return (
    <div role="status" className="mt-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-900">
      <p>{issuedMessage(issued, emailRequested)}</p>
      <label className="mt-2 block font-medium" htmlFor="invite-link">
        Invite link for {issued.invite.email}
      </label>
      <div className="mt-1 flex gap-2">
        <input id="invite-link" readOnly value={issued.link} className={`${INPUT} mt-0 font-mono text-xs`} />
        <button
          type="button"
          className={BUTTON}
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
      {copied === "yes" && <p className="mt-1">Link copied.</p>}
      {copied === "failed" && <p className="mt-1">Couldn't copy. Select the link and copy it yourself.</p>}
      <p className="mt-1">The link works once and expires on {day(issued.invite.expires_at)}.</p>
    </div>
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
    <form onSubmit={onSubmit} aria-label="Invite someone" className="max-w-md space-y-4">
      <h2 className="text-lg font-semibold">Invite someone</h2>
      <FormError message={failure(createInvite.error)} />
      <div>
        <label htmlFor="invite-email" className="block text-sm font-medium">
          Email
        </label>
        <input id="invite-email" name="email" type="email" required autoComplete="off" className={INPUT} />
      </div>
      <div>
        <label htmlFor="invite-role" className="block text-sm font-medium">
          Role
        </label>
        <select id="invite-role" name="role" defaultValue="editor" className={INPUT}>
          <option value="editor">Editor</option>
          <option value="owner">Owner</option>
        </select>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="send_email" defaultChecked />
        Email the invite link
      </label>
      <button
        type="submit"
        disabled={createInvite.isPending}
        className="rounded bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-700 disabled:bg-slate-600"
      >
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
  const busy = renew.isPending || revoke.isPending;
  return (
    <tr className="border-t border-slate-200 align-top">
      <td className="py-2 pr-4">{invite.email}</td>
      <td className="py-2 pr-4">{ROLE_NAMES[invite.role]}</td>
      <td className="py-2 pr-4">{invite.invited_by.name}</td>
      <td className="py-2 pr-4">{invite.expired ? "Expired" : day(invite.expires_at)}</td>
      <td className="py-2">
        <div className="flex gap-2">
          <button
            type="button"
            className={BUTTON}
            disabled={busy}
            aria-label={`New link for ${invite.email}`}
            onClick={() => {
              renew.mutate(invite.id, { onSuccess: onIssued });
            }}
          >
            New link
          </button>
          <button
            type="button"
            className={BUTTON}
            disabled={busy}
            aria-label={`Revoke invite for ${invite.email}`}
            onClick={() => {
              revoke.mutate(invite.id);
            }}
          >
            Revoke
          </button>
        </div>
        {(renew.isError || revoke.isError) && (
          <p role="alert" className="mt-1 text-sm text-red-800">
            That didn't work. The invite may have been accepted or revoked already.
          </p>
        )}
      </td>
    </tr>
  );
}

function PendingInvites({ organisationId, onIssued }: { organisationId: string; onIssued: (issued: IssuedInvite) => void }) {
  const invites = usePendingInvites(organisationId);
  if (invites.isPending) return <p role="status">Loading invites…</p>;
  if (invites.isError) return <p role="alert">The pending invites could not be loaded. Try again shortly.</p>;
  if (invites.data.length === 0) return <p className="text-slate-700">No pending invites.</p>;
  return (
    <table className="w-full text-left text-sm" aria-label="Pending invites">
      <thead>
        <tr>
          <th className="py-2 pr-4 font-medium">Email</th>
          <th className="py-2 pr-4 font-medium">Role</th>
          <th className="py-2 pr-4 font-medium">Invited by</th>
          <th className="py-2 pr-4 font-medium">Expires</th>
          <th className="py-2 font-medium">
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
  );
}

/** Members tab: Owners see and manage Members, invite people and manage pending invites. */
export function MembersPage({ organisationId, memberId, isOwner }: { organisationId: string; memberId: string; isOwner: boolean }) {
  const [issued, setIssued] = useState<{ invite: IssuedInvite; emailed: boolean } | null>(null);
  if (!isOwner) return <p>Only Owners can manage Members and invites.</p>;
  return (
    <section aria-labelledby="members-heading">
      <h2 id="members-heading" className="text-lg font-semibold">
        Members
      </h2>
      <div className="mt-2 mb-8">
        <MembersList organisationId={organisationId} memberId={memberId} />
      </div>
      <InviteForm
        organisationId={organisationId}
        onIssued={(invite, emailed) => {
          setIssued({ invite, emailed });
        }}
      />
      {issued && <InviteLink key={issued.invite.link} issued={issued.invite} emailRequested={issued.emailed} />}
      <h2 className="mt-8 text-lg font-semibold">Pending invites</h2>
      <div className="mt-2">
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
