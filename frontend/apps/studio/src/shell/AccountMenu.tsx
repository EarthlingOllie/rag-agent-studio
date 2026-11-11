import { Link, useNavigate } from "@tanstack/react-router";

import { type Session, useSignOut } from "../auth/session";
import { Avatar, Menu, type MenuItem } from "../design";

/**
 * The Member's avatar, opening their Profile, Security and Sign out. Its name is "<Member>, Account", so the
 * Member's name stays in the top bar for screen readers. Profile and Security need an Organisation
 * to sit in.
 */
export function AccountMenu({ session, organisationId, inOrganisation }: {
  session: Session;
  organisationId: string;
  inOrganisation: boolean;
}) {
  const signOut = useSignOut();
  const navigate = useNavigate();
  const items: MenuItem[] = [
    ...(inOrganisation
      ? [
          {
            label: "Profile",
            renderLink: (props) => <Link to="/organisations/$organisationId/profile" params={{ organisationId }} {...props} />,
          } satisfies MenuItem,
          {
            label: "Security",
            renderLink: (props) => <Link to="/organisations/$organisationId/security" params={{ organisationId }} {...props} />,
          } satisfies MenuItem,
        ]
      : []),
    {
      label: "Sign out",
      disabled: signOut.isPending,
      onSelect: () => {
        signOut.mutate(undefined, {
          onSuccess: () => {
            void navigate({ to: "/sign-in" });
          },
        });
      },
    },
  ];
  return (
    <>
      {signOut.isError && (
        <p role="alert" className="text-sm text-danger">
          Sign-out failed. Try again.
        </p>
      )}
      <Menu
        // The name is hidden text, "<Member>, Account", not aria-label: the initials are visible
        // text, and a label that didn't contain them would fail WCAG 2.5.3 (label in name). The
        // avatar is a picture of the same name, so it is hidden from assistive technology.
        label={
          <>
            <span aria-hidden="true">
              <Avatar name={session.member.name} />
            </span>
            <span className="sr-only">{`${session.member.name}, Account`}</span>
          </>
        }
        menuLabel="Account"
        align="end"
        triggerClassName="rounded-full"
        items={items}
      />
    </>
  );
}
