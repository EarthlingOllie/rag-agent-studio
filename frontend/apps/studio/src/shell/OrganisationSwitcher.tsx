import { useNavigate } from "@tanstack/react-router";

import { type Session, useSwitchOrganisation } from "../auth/session";

/**
 * The open Organisation's name, or, for a Member of several, a switcher between them. Switching
 * is remembered by the API and opens the chosen Organisation's Projects: every page below it
 * reads that Organisation from the address, so nothing from the previous one stays on screen.
 */
export function OrganisationSwitcher({ session, organisationId }: { session: Session; organisationId: string }) {
  const switchOrganisation = useSwitchOrganisation();
  const navigate = useNavigate();
  const current = session.organisations.find((organisation) => organisation.id === organisationId);

  if (session.organisations.length < 2) {
    return current ? <span className="text-sm text-muted">{current.name}</span> : null;
  }
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="organisation-switcher" className="sr-only">
        Organisation
      </label>
      <select
        id="organisation-switcher"
        value={organisationId}
        disabled={switchOrganisation.isPending}
        onChange={(event) => {
          switchOrganisation.mutate(event.target.value, {
            onSuccess: (updated) => {
              void navigate({
                to: "/organisations/$organisationId/projects",
                params: { organisationId: updated.active_organisation_id as string },
              });
            },
          });
        }}
        className="rounded border border-field bg-surface px-2 py-1 text-sm"
      >
        {current === undefined && <option value={organisationId}>Choose an Organisation</option>}
        {session.organisations.map((organisation) => (
          <option key={organisation.id} value={organisation.id}>
            {organisation.name}
          </option>
        ))}
      </select>
      {switchOrganisation.isError && (
        <p role="alert" className="text-sm text-danger">
          Couldn't switch Organisation. Try again.
        </p>
      )}
    </div>
  );
}
