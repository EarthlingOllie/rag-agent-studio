"""Applies one mutation at a time to the 01-06 worktree, runs the throttling tests, restores."""
import subprocess, sys
WT = sys.argv[1]
T = "tests/integration/test_sign_in_throttling.py"
MUTATIONS = [
    ("unknown emails don't count on the account counter", "app/auth/throttle.py",
     "        for scope, key in self._keys(email, ip).items():\n            failures = int(",
     "        for scope, key in self._keys(email, ip).items():\n            if scope is CounterScope.ACCOUNT and not email.startswith('member-'):\n                continue\n            failures = int("),
    ("a stale counter is never reset", "app/auth/throttle.py",
     "  redis.call('DEL', KEYS[1])\n", "  redis.call('EXISTS', KEYS[1])\n"),
    ("success doesn't clear the account counter", "app/auth/throttle.py",
     "        await self._redis.delete(self._keys(email, ip)[CounterScope.ACCOUNT])", "        return None"),
    ("refused attempts are counted", "app/auth/service.py",
     "        raise SignInThrottledError(refusal)", "        await throttle.record_failure(email, ip)\n        raise SignInThrottledError(refusal)"),
    ("no per-IP counter", "app/auth/throttle.py",
     "            CounterScope.IP: f\"{_KEY_PREFIX}ip:{ip}\",", "            CounterScope.IP: f\"{_KEY_PREFIX}ip:everyone-{email}\","),
    ("constant delay instead of progressive", "app/auth/throttle.py",
     "2 ** (failures - limits.delay_after)", "1"),
    ("lockout ignores SIGN_IN_LOCKOUT_SECONDS", "app/auth/throttle.py",
     "self._lockout_seconds = settings.sign_in_lockout_seconds", "self._lockout_seconds = 900"),
    ("lockout not audited", "app/auth/service.py",
     "    await session.commit()\n", "    await session.rollback()\n"),
    ("delay refuses nothing (correct password gets through)", "app/auth/throttle.py",
     "            if remaining > 0:", "            if remaining > 0 and locked:"),
]
backend = f"{WT}/backend"
caught = 0
for name, path, old, new in MUTATIONS:
    full = f"{backend}/{path}"
    src = open(full).read()
    assert src.count(old) == 1, (name, old)
    open(full, "w").write(src.replace(old, new))
    try:
        r = subprocess.run(["uv", "run", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider", T],
                           cwd=backend, capture_output=True, text=True)
    finally:
        open(full, "w").write(src)
    failed = [l.split(" - ")[0].replace("FAILED ", "") for l in r.stdout.splitlines() if l.startswith("FAILED")]
    status = "CAUGHT" if r.returncode != 0 else "SURVIVED"
    caught += r.returncode != 0
    print(f"== mutation: {name}\n   {status}; failing tests:")
    for f in failed:
        print(f"     {f.split('::')[-1]}")
print(f"\n{caught}/{len(MUTATIONS)} mutations caught")
r = subprocess.run(["uv", "run", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider", T], cwd=backend, capture_output=True, text=True)
print("unmodified code:", r.stdout.strip().splitlines()[-1])
