import { Notice } from "../design";
import { type ExpectedSourceDependents, useExpectedSources } from "./documents";

/** "A", "A and B", "A, B and C". */
function listed(items: string[]): string {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.slice(-1).join("")}`;
}

/**
 * The Expected source warning: which Agents' Evaluation Sets, and how many of their cases, hold
 * an Expected source in a Document, then what the change does to them. Nothing when none do. It
 * warns; it never blocks.
 */
export function ExpectedSourceWarning({
  dependents,
  consequence,
}: {
  dependents: ExpectedSourceDependents | undefined;
  consequence: string;
}) {
  if (!dependents || dependents.agents.length === 0) return null;
  const agents = dependents.agents.map(
    ({ name, case_count: count }) => `${name} (${String(count)} ${count === 1 ? "case" : "cases"})`,
  );
  return (
    <Notice tone="warning">
      Expected sources in this Document are used by {listed(agents)}. {consequence}
    </Notice>
  );
}

export const DELETING_CONSEQUENCE = "Deleting it makes them Stale expectations, skipped by Runs until fixed.";
export const NEW_EDITION_CONSEQUENCE =
  "Any whose passage isn't in the new edition becomes a Stale expectation, skipped by Runs until fixed.";

/** The warning in a Document's delete confirmation, read when the confirmation opens. */
export function DeletionWarning({ organisationId, projectId, documentId }: { organisationId: string; projectId: string; documentId: string }) {
  const dependents = useExpectedSources(organisationId, projectId, documentId);
  return <ExpectedSourceWarning dependents={dependents.data} consequence={DELETING_CONSEQUENCE} />;
}
