#!/usr/bin/env bash
# Each mutation breaks one acceptance criterion; the named tests must fail. The tree is restored after each.
set -u
WT=$1; cd "$WT"
export TEST_REDIS_URL=redis://localhost:6379/9
export TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:5432/studio_test_0107
run() { # name, file, old, new, test command
  local name=$1 file=$2 old=$3 new=$4; shift 4
  echo "=== mutation: $name ($file)"
  python3 - "$file" "$old" "$new" <<'PY'
import sys; p,o,n=sys.argv[1:]; s=open(p).read(); assert o in s, "pattern missing"; open(p,'w').write(s.replace(o,n,1))
PY
  (eval "$@") > /tmp/mut0107.out 2>&1; rc=$?
  grep -E "^(FAILED|ERROR)|passed|failed" /tmp/mut0107.out | head -8
  echo "exit=$rc (non-zero = mutation caught)"
  git checkout -q -- "$file"
}
B="cd backend && uv run pytest -q -p no:cacheprovider --no-cov tests/integration/test_password_reset.py tests/integration/test_profile.py tests/integration/test_password_audit_events.py tests/integration/test_mailer.py"
run "reset links reusable" backend/app/auth/service.py 'PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at' 'PasswordResetToken.expires_at' "$B"
run "reset links never expire" backend/app/auth/service.py 'PasswordResetToken.expires_at > now,' '' "$B"
run "token stored in plain text" backend/app/auth/service.py 'member_id=member.id, token_hash=_token_hash(token), expires_at' 'member_id=member.id, token_hash=token, expires_at' "$B"
run "unknown email answered differently" backend/app/auth/account_api.py '    return PasswordResetAccepted(detail=RESET_ACCEPTED)' '    return PasswordResetAccepted(detail=RESET_ACCEPTED + body.email[:0] + ("" if "nobody" not in body.email else " "))' "$B"
run "reset keeps other sessions" backend/app/auth/account_api.py '        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_RESET_LINK) from None
    await sessions.delete_all(member.id)' '        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_RESET_LINK) from None' "$B"
run "password change keeps other sessions" backend/app/auth/account_api.py '        raise HTTPException(status.HTTP_400_BAD_REQUEST, WRONG_CURRENT_PASSWORD) from None
    await sessions.delete_all(member.id)' '        raise HTTPException(status.HTTP_400_BAD_REQUEST, WRONG_CURRENT_PASSWORD) from None' "$B"
run "current password not checked" backend/app/auth/service.py 'if not verify_password(member.password_hash, current_password):' 'if False:' "$B"
run "reset not audited" backend/app/auth/service.py 'await _record_security_event(session, member, "member.password_reset", now)' 'pass' "$B"
run "password change not audited" backend/app/auth/service.py 'await _record_security_event(session, member, "member.password_changed", now)' 'pass' "$B"
run "settings ignored by mailer factory" backend/app/mail/factory.py 'if settings.mailer == "outbox":' 'if True:' "$B"
F="cd frontend && pnpm exec vitest run apps/studio/src/profile apps/studio/src/auth"
run "Profile sends no current password" frontend/apps/studio/src/profile/ProfilePage.tsx 'formValues(form, ["current_password", "new_password"])' '{ current_password: "", ...formValues(form, ["new_password"]) }' "$F"
run "no forgot-password link" frontend/apps/studio/src/auth/SignInPage.tsx 'Forgot your password?' 'Trouble signing in?' "$F"
echo "=== unmodified tree"
(eval "$B") 2>&1 | tail -1
(eval "$F") 2>&1 | grep -E "Tests " 
