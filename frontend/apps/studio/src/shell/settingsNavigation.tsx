import { useMatchRoute } from "@tanstack/react-router";

export const SETTINGS = "/organisations/$organisationId/settings";

type SettingsPath =
  | "/organisations/$organisationId/settings"
  | "/organisations/$organisationId/settings/credentials"
  | "/organisations/$organisationId/settings/models"
  | "/organisations/$organisationId/settings/theme"
  | "/organisations/$organisationId/settings/members"
  | "/organisations/$organisationId/settings/audit";

/** Organisation settings' areas, in order. Members and Audit are for Owners. */
export const SETTINGS_AREAS: { label: string; to: SettingsPath; ownersOnly?: true }[] = [
  { label: "General", to: SETTINGS },
  { label: "Credentials", to: `${SETTINGS}/credentials` },
  { label: "Models", to: `${SETTINGS}/models` },
  { label: "Theme", to: `${SETTINGS}/theme` },
  { label: "Members", to: `${SETTINGS}/members`, ownersOnly: true },
  { label: "Audit", to: `${SETTINGS}/audit`, ownersOnly: true },
];

/**
 * Organisation settings' areas, each with whether the Member is in it now: the tabs under the
 * settings header and the breadcrumb's last crumb. An address under settings that is none of them
 * (a page that was not found) has no current area.
 */
export function useSettingsAreas(organisationId: string) {
  const matchRoute = useMatchRoute();
  // General is the index route, so each area is matched exactly (a trailing slash still matches).
  return SETTINGS_AREAS.map((area) => ({ ...area, current: matchRoute({ to: area.to, params: { organisationId } }) !== false }));
}
