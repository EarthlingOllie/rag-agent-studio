# Hand-rolled Studio authentication instead of Cognito or a third-party IdP

Members sign in with email and password (argon2 hashes, httpOnly cookie sessions). Organisations are created by self-serve sign-up, and further Members join by invite link. We passed on Cognito and Auth0/Clerk because they are awkward to run locally and to fake for 100% coverage, and because owning the auth flow is part of what this project demonstrates. SSO is explicitly out of scope.
