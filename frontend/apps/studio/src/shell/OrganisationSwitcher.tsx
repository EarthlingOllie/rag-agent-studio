import { useNavigate } from "@tanstack/react-router";

import { type Session, useSwitchOrganisation } from "../auth/session";
import { CrumbSwitcher, CrumbText } from "../design";

/**
 * The breadcrumb's first crumb: the open Organisation's name, or, for a
 * Member of several, a switcher between them. Switching is remembered by the API and opens the
 * chosen Organisation's Projects: every page below it reads that Organisation from the address,
 * so nothing from the previous one stays on screen.
 */
export function OrganisationCrumb({ session, organisationId }: { session: Session; organisationId: string }) {
  const switchOrganisation = useSwitchOrganisation();
  const navigate = useNavigate();
  const current = session.organisations.find((organisation) => organisation.id === organisationId);

  if (session.organisations.length < 2) {
    return current ? <CrumbText>{current.name}</CrumbText> : null;
  }
  return (
    <span className="flex items-center gap-2">
      <CrumbSwitcher
        label={current?.name ?? "Choose an Organisation"}
        menuLabel="Organisations"
        disabled={switchOrganisation.isPending}
        items={session.organisations.map((organisation) => ({
          id: organisation.id,
          label: organisation.name,
          current: organisation.id === organisationId,
          onSelect: () => {
            if (organisation.id === organisationId) return;
            switchOrganisation.mutate(organisation.id, {
              onSuccess: (updated) => {
                void navigate({
                  to: "/organisations/$organisationId/projects",
                  params: { organisationId: updated.active_organisation_id as string },
                });
              },
            });
          },
        }))}
      />
      {switchOrganisation.isError && (
        <span role="alert" className="text-sm text-danger">
          Couldn't switch Organisation. Try again.
        </span>
      )}
    </span>
  );
}
