import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { memberFailure, type OrganisationMember, type Role, useChangeRole, useMembers, useRemoveMember } from "./members";

const BUTTON = "rounded border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100 disabled:text-slate-600";
const SELECT = "rounded border border-slate-400 bg-white px-2 py-1 text-sm focus:outline-2 focus:outline-slate-900";

function MemberRow({
  member,
  isYou,
  busy,
  onChangeRole,
  onRemove,
}: {
  member: OrganisationMember;
  isYou: boolean;
  busy: boolean;
  onChangeRole: (role: Role) => void;
  onRemove: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  return (
    <tr className="border-t border-slate-200 align-top">
      <td className="py-2 pr-4">
        {member.name}
        {isYou && " (you)"}
      </td>
      <td className="py-2 pr-4">{member.email}</td>
      <td className="py-2 pr-4">
        <select
          aria-label={`Role for ${member.name}`}
          className={SELECT}
          value={member.role}
          disabled={busy}
          onChange={(event) => {
            onChangeRole(event.target.value as Role);
          }}
        >
          <option value="owner">Owner</option>
          <option value="editor">Editor</option>
        </select>
      </td>
      <td className="py-2">
        {!isYou &&
          (confirming ? (
            <div className="flex gap-2">
              <button
                type="button"
                className={BUTTON}
                disabled={busy}
                onClick={() => {
                  setConfirming(false);
                  onRemove();
                }}
              >
                Yes, remove {member.name}
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
          ) : (
            <button
              type="button"
              className={BUTTON}
              disabled={busy}
              aria-label={`Remove ${member.name}`}
              onClick={() => {
                setConfirming(true);
              }}
            >
              Remove
            </button>
          ))}
      </td>
    </tr>
  );
}

/** The Members of the Organisation with their roles; Owners change roles and remove Members here. */
export function MembersList({ organisationId, memberId }: { organisationId: string; memberId: string }) {
  const members = useMembers(organisationId);
  const changeRole = useChangeRole(organisationId);
  const removeMember = useRemoveMember(organisationId);
  const [done, setDone] = useState<string | null>(null);
  if (members.isPending) return <p role="status">Loading Members…</p>;
  if (members.isError) return <p role="alert">The Members could not be loaded. Try again shortly.</p>;
  const busy = changeRole.isPending || removeMember.isPending;
  const error = changeRole.error ?? removeMember.error;
  return (
    <div className="space-y-3">
      <FormError message={memberFailure(error)} />
      {done && <p className="text-sm text-green-900">{done}</p>}
      <table className="w-full text-left text-sm" aria-label="Members">
        <thead>
          <tr>
            <th className="py-2 pr-4 font-medium">Name</th>
            <th className="py-2 pr-4 font-medium">Email</th>
            <th className="py-2 pr-4 font-medium">Role</th>
            <th className="py-2 font-medium">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {members.data.map((member) => (
            <MemberRow
              key={member.id}
              member={member}
              isYou={member.id === memberId}
              busy={busy}
              onChangeRole={(role) => {
                setDone(null);
                removeMember.reset();
                changeRole.mutate(
                  { memberId: member.id, role },
                  {
                    onSuccess: (changed) => {
                      setDone(`${changed.name} is now ${changed.role === "owner" ? "an Owner" : "an Editor"}.`);
                    },
                  },
                );
              }}
              onRemove={() => {
                setDone(null);
                changeRole.reset();
                removeMember.mutate(member.id, {
                  onSuccess: () => {
                    setDone(`${member.name} was removed and can no longer open this Organisation.`);
                  },
                });
              }}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
