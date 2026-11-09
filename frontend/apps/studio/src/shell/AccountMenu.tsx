import { Link, useNavigate } from "@tanstack/react-router";

import { type Session, useSignOut } from "../auth/session";
import { Avatar, Menu, type MenuItem } from "../design";

/**
 * The Member's avatar, opening Profile and Sign out. Its name is "<Member>, Account", so the
 * Member's name stays in the top bar for screen readers. Profile needs an Organisation to sit in.
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
        label={<Avatar name={session.member.name} />}
        triggerLabel={`${session.member.name}, Account`}
        menuLabel="Account"
        align="end"
        triggerClassName="rounded-full"
        items={items}
      />
    </>
  );
}
