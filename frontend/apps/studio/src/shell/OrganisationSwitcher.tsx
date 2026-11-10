import { useNavigate } from "@tanstack/react-router";

import { type Session, useSwitchOrganisation } from "../auth/session";
import { CrumbSwitcher, CrumbText, Icon, Menu, type MenuItem, sidebarSwitcher, SidebarTitle } from "../design";

/**
 * The Organisation switcher's menu: the Member's Organisations, the open one marked. Switching is
 * remembered by the API and opens the chosen Organisation's Projects: every page below it reads
 * that Organisation from the address, so nothing from the previous one stays on screen.
 */
function useOrganisationSwitcher(session: Session, organisationId: string) {
  const switchOrganisation = useSwitchOrganisation();
  const navigate = useNavigate();
  const items: MenuItem[] = session.organisations.map((organisation) => ({
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
  }));
  const current = session.organisations.find((organisation) => organisation.id === organisationId);
  return {
    items,
    current,
    /** The switcher's label: the open Organisation, or a prompt on one the Member doesn't belong to. */
    label: current?.name ?? "Choose an Organisation",
    /** Only a Member of several Organisations has anything to switch to. */
    switches: session.organisations.length > 1,
    pending: switchOrganisation.isPending,
    failed: switchOrganisation.isError,
  };
}

function SwitchFailed() {
  return (
    <span role="alert" className="text-sm text-danger">
      Couldn't switch Organisation. Try again.
    </span>
  );
}

/** The breadcrumb's first crumb: the open Organisation's name, or, for a Member of several, a switcher between them. */
export function OrganisationCrumb({ session, organisationId }: { session: Session; organisationId: string }) {
  const switcher = useOrganisationSwitcher(session, organisationId);
  if (!switcher.switches) {
    return switcher.current ? <CrumbText>{switcher.current.name}</CrumbText> : null;
  }
  return (
    <span className="flex items-center gap-2">
      <CrumbSwitcher
        label={switcher.label}
        menuLabel="Organisations"
        disabled={switcher.pending}
        items={switcher.items}
      />
      {switcher.failed && <SwitchFailed />}
    </span>
  );
}

/** The top of the sidebar: the same switcher as a full-width row, or the one Organisation's name as plain text. */
export function SidebarOrganisation({ session, organisationId }: { session: Session; organisationId: string }) {
  const switcher = useOrganisationSwitcher(session, organisationId);
  if (!switcher.switches) {
    return switcher.current ? <SidebarTitle>{switcher.current.name}</SidebarTitle> : null;
  }
  const { label } = switcher;
  return (
    <div className="flex flex-col gap-1">
      <Menu
        label={
          <>
            <span className="truncate">{label}</span>
            <Icon name="chevronDown" size={14} className="shrink-0 text-muted" />
          </>
        }
        triggerLabel={`${label}, Organisations`}
        menuLabel="Organisations"
        triggerClassName={sidebarSwitcher}
        wrapperClassName="relative flex"
        disabled={switcher.pending}
        items={switcher.items}
      />
      {switcher.failed && <SwitchFailed />}
    </div>
  );
}
