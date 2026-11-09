import { Link, useMatchRoute } from "@tanstack/react-router";

import { CrumbSwitcher, type IconName, type MenuItem } from "../design";

type SettingsPath =
  | "/organisations/$organisationId/settings"
  | "/organisations/$organisationId/settings/credentials"
  | "/organisations/$organisationId/settings/models"
  | "/organisations/$organisationId/settings/theme"
  | "/organisations/$organisationId/settings/members"
  | "/organisations/$organisationId/settings/audit";

/** Organisation settings' areas, in menu order. Members and Audit are for Owners, as the tabs had them. */
const AREAS: { label: string; icon: IconName; to: SettingsPath; ownersOnly?: true }[] = [
  { label: "General", icon: "settings", to: "/organisations/$organisationId/settings" },
  { label: "Credentials", icon: "key", to: "/organisations/$organisationId/settings/credentials" },
  { label: "Models", icon: "model", to: "/organisations/$organisationId/settings/models" },
  { label: "Theme", icon: "palette", to: "/organisations/$organisationId/settings/theme" },
  { label: "Members", icon: "members", to: "/organisations/$organisationId/settings/members", ownersOnly: true },
  { label: "Audit", icon: "history", to: "/organisations/$organisationId/settings/audit", ownersOnly: true },
];

/**
 * The Settings switcher crumb, after "Settings ▾" on an Organisation settings page: the area the
 * Member is in (current), with its siblings as links. It replaces the settings tab row. Members
 * and Audit are left out for anyone but an Owner; an Editor who opens one by its address still
 * gets a crumb for it.
 */
export function SettingsCrumb({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const matchRoute = useMatchRoute();
  const areas = AREAS.map((area) => ({
    area,
    // General is the index route, so it is matched exactly; the rest also match a trailing slash.
    current: matchRoute({ to: area.to, params: { organisationId } }) !== false,
  }));
  // An address under settings that is none of the areas is a page that was not found.
  const here = areas.find(({ current }) => current)?.area.label ?? "Not found";
  const items: MenuItem[] = areas
    .filter(({ area }) => area.ownersOnly !== true || isOwner)
    .map(({ area, current }) => ({
      label: area.label,
      icon: area.icon,
      current,
      renderLink: (props) => <Link to={area.to} params={{ organisationId }} {...props} />,
    }));
  return <CrumbSwitcher label={here} menuLabel="Organisation settings" items={items} current />;
}
