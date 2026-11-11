"""Mutation proof for 03-01: apply each mutation, run the tests that should catch it, restore.

Usage: python3 mutate.py <worktree>. Each mutation must make at least one test fail; at the end
the unmodified code must pass the same tests.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
BACKEND = ["uv", "run", "pytest", "-q", "--no-cov", "-x",
           "tests/integration/test_projects.py", "tests/integration/test_tenant_isolation.py"]
FRONTEND = ["npx", "vitest", "run", "apps/studio/src/projects"]
SERVICE = "backend/app/projects/service.py"
API = "backend/app/projects/api.py"

MUTATIONS = [
    ("Projects found in any Organisation", SERVICE,
     "Project.id == project_id, Project.organisation_id == scope.organisation_id",
     "Project.id == project_id"),
    ("List shows every Organisation's Projects", SERVICE,
     ".where(Project.organisation_id == scope.organisation_id, archived_filter)",
     ".where(archived_filter)"),
    ("Archived Projects stay in the main list", SERVICE,
     "archived_at.is_not(None) if archived else archived_at.is_(None)",
     "archived_at.is_not(None) if archived else archived_at.is_not(None) | archived_at.is_(None)"),
    ("Not sorted by name", SERVICE,
     ".order_by(func.lower(Project.name), Project.created_at)", ".order_by(Project.created_at)"),
    # Not listed: sorting by Project.name instead of lower(name) is an equivalent mutation on a
    # database with an en_US collation (as in docker compose), which already sorts case together.
    ("Archived Projects can be changed", SERVICE,
     "    if project.archived_at is not None:\n        raise ProjectArchivedError\n", ""),
    ("Archive doesn't set archived_at", SERVICE,
     "    project.archived_at = now\n", ""),
    ("Restore of an active Project allowed", SERVICE,
     "    if project.archived_at is None:\n        raise ProjectNotArchivedError\n", ""),
    ("Restore keeps the Project archived", SERVICE,
     "    project.archived_at = None\n", ""),
    ("Rename ignores the name", SERVICE,
     "        project.name = name\n", "        pass\n"),
    ("Description not saved on edit", SERVICE,
     "        project.description = description\n", "        pass\n"),
    ("Creation not audited", SERVICE, 'action="project.created"', 'action="project.added"'),
    ("Archive not audited", SERVICE, 'action="project.archived"', 'action="project.hidden"'),
    ("Restore audited with the wrong actor", SERVICE,
     '''        actor_id=scope.member_id,
        action="project.restored",''', '''        actor_id=None,
        action="project.restored",'''),
    ("Restore open to Editors", API,
     "project_id: uuid.UUID, scope: OwnerScope, db: Db, clock: ClockDep",
     "project_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep"),
    ("Names not trimmed", API, "StringConstraints(strip_whitespace=True, min_length=1",
     "StringConstraints(strip_whitespace=False, min_length=1"),
    ("Archived Project answers 404 not 409", API,
     "    except service.ProjectArchivedError:\n        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None\n    return await _respond(project)\n\n\n@router.post(\n    \"/projects/{project_id}/archive\",",
     "    except service.ProjectArchivedError:\n        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None\n    return await _respond(project)\n\n\n@router.post(\n    \"/projects/{project_id}/archive\","),
    ("Restore offered to Editors in the list", "frontend/apps/studio/src/projects/ProjectsPage.tsx",
     "                  {isOwner && (", "                  {(isOwner || true) && ("),
    ("Restore offered to Editors on the page", "frontend/apps/studio/src/projects/ProjectPage.tsx",
     "      {isOwner && (\n        <button", "      {(isOwner || true) && (\n        <button"),
    ("Archive without confirming", "frontend/apps/studio/src/projects/ProjectPage.tsx",
     "            archive.reset();\n            setConfirming(true);",
     "            archive.mutate(project.id);"),
    ("A tab missing", "frontend/apps/studio/src/projects/ProjectPage.tsx",
     '  { label: "Conversations", to: `${PROJECT}/conversations` },\n', ""),
    ("Counts swapped", "frontend/apps/studio/src/projects/ProjectsPage.tsx",
     '<td className="py-2 pr-4 text-right">{project.document_count}</td>',
     '<td className="py-2 pr-4 text-right">{project.agent_count}</td>'),
    ("Archived refusal shown as a generic error", "frontend/apps/studio/src/projects/projects.ts",
     "error.status === 409 && error.detail", "error.status === 999 && error.detail"),
    ("Lists not refreshed after a change", "frontend/apps/studio/src/projects/projects.ts",
     '    await queryClient.invalidateQueries({ queryKey: [...projectsKey(organisationId), "list"] });\n',
     ""),
]


def run(command: list[str], cwd: Path) -> bool:
    return subprocess.run(command, cwd=cwd, capture_output=True).returncode == 0


failures = 0
for name, file, old, new in MUTATIONS:
    path = ROOT / file
    original = path.read_text()
    assert original.count(old) == 1, (name, old)
    path.write_text(original.replace(old, new))
    try:
        backend = file.startswith("backend/")
        passed = run(BACKEND, ROOT / "backend") if backend else run(FRONTEND, ROOT / "frontend")
    finally:
        path.write_text(original)
    print(f"{'SURVIVED' if passed else 'caught  '}  {name}  ({file})", flush=True)
    failures += passed

clean = run(BACKEND, ROOT / "backend") and run(FRONTEND, ROOT / "frontend")
print(f"unmodified code passes: {clean}")
print(f"{len(MUTATIONS) - failures}/{len(MUTATIONS)} mutations caught")
sys.exit(0 if failures == 0 and clean else 1)
