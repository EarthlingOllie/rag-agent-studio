import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, ConfirmDialog, field, table, text, useToast } from "../design";
import { memberFailure, type OrganisationMember, type Role, useChangeRole, useMembers, useRemoveMember } from "./members";


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
  return (
    <tr className={table.row}>
      <td className={`${table.td} font-medium`}>
        {member.name}
        {isYou && " (you)"}
      </td>
      <td className={table.tdMuted}>{member.email}</td>
      <td className={table.td}>
        <select
          aria-label={`Role for ${member.name}`}
          className={field.selectCompact}
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
      <td className={`${table.td} text-right`}>
        {!isYou && (
          <button type="button" className={button.danger} disabled={busy} aria-label={`Remove ${member.name}`} onClick={onRemove}>
            Remove
          </button>
        )}
      </td>
    </tr>
  );
}

/**
 * The Members of the Organisation with their roles; Owners change roles and remove Members here.
 * A removal is confirmed first; every change is confirmed by a toast.
 */
export function MembersList({
  organisationId,
  organisationName,
  memberId,
}: {
  organisationId: string;
  organisationName: string;
  memberId: string;
}) {
  const members = useMembers(organisationId);
  const changeRole = useChangeRole(organisationId);
  const removeMember = useRemoveMember(organisationId);
  const toast = useToast();
  const [removing, setRemoving] = useState<OrganisationMember | null>(null);
  if (members.isPending) return <p role="status" className={text.muted}>Loading Members…</p>;
  if (members.isError) return <p role="alert" className={text.muted}>The Members could not be loaded. Try again shortly.</p>;
  const busy = changeRole.isPending || removeMember.isPending;
  const error = changeRole.error ?? removeMember.error;
  return (
    <div className="flex flex-col gap-3">
      <FormError message={memberFailure(error)} />
      <div className={table.wrap}>
        <table className={table.table} aria-label="Members">
          <thead>
            <tr>
              <th className={table.th}>Name</th>
              <th className={table.th}>Email</th>
              <th className={table.th}>Role</th>
              <th className={table.th}>
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
                  removeMember.reset();
                  changeRole.mutate(
                    { memberId: member.id, role },
                    {
                      onSuccess: (changed) => {
                        toast.show(`${changed.name} is now ${changed.role === "owner" ? "an Owner" : "an Editor"}.`);
                      },
                    },
                  );
                }}
                onRemove={() => {
                  setRemoving(member);
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
      <ConfirmDialog
        open={removing !== null}
        title={`Remove ${removing?.name ?? ""}?`}
        confirmLabel={`Yes, remove ${removing?.name ?? ""}`}
        destructive
        onCancel={() => {
          setRemoving(null);
        }}
        onConfirm={() => {
          const member = removing as OrganisationMember;
          setRemoving(null);
          changeRole.reset();
          removeMember.mutate(member.id, {
            onSuccess: () => {
              toast.show(`${member.name} was removed and can no longer open this Organisation.`);
            },
          });
        }}
      >
        {removing?.name} loses access to {organisationName} and its Projects straight away. Invite them again to bring them back.
      </ConfirmDialog>
    </div>
  );
}
