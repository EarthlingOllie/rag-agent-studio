import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  type Project,
  projectFailure,
  useProject,
  useUpdateProject,
} from "./projects";
import { useOrganisationRole } from "./ProjectsPage";

function OcrSetting({
  project,
  organisationId,
}: {
  project: Project;
  organisationId: string;
}) {
  const update = useUpdateProject(organisationId, project.id);
  const archived = project.archived_at !== null;
  // The setting asked for while it saves. Kept in component state, set in the click itself, so
  // the box shows it at once instead of after the mutation's state catches up.
  const [requested, setRequested] = useState<boolean | null>(null);
  return (
    <fieldset className="max-w-xl space-y-2 rounded border border-line p-4">
      <legend className="px-1 font-medium">OCR</legend>
      <FormError message={projectFailure(update.error)} />
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          // While a change saves (the box is disabled meanwhile), it shows the setting asked for.
          checked={requested ?? project.ocr_enabled}
          disabled={archived || requested !== null}
          onChange={(event) => {
            setRequested(event.target.checked);
            update.mutate(
              { ocr_enabled: event.target.checked },
              {
                onSettled: () => {
                  setRequested(null);
                },
              },
            );
          }}
          className="h-4 w-4"
        />
        Read scanned PDFs with OCR
      </label>
      <p id="ocr-help" className="text-sm text-muted">
        OCR reads text in images, such as scanned pages. It makes processing
        slower, so leave it off unless this Project has scanned PDFs.
      </p>
      <p role="status" className="text-sm text-muted">
        {project.ocr_enabled
          ? "OCR is on. New uploads are read with OCR. Retry a Document on the Documents tab to reprocess it."
          : "OCR is off. Text in images isn't read."}
      </p>
    </fieldset>
  );
}

type FlaggedChunkMode = Project["flagged_chunk_mode"];

const FLAGGED_CHUNK_OPTIONS: { mode: FlaggedChunkMode; label: string }[] = [
  { mode: "mark", label: "Mark them, and keep retrieving them" },
  { mode: "exclude", label: "Exclude them from retrieval" },
];

/**
 * The Flagged Chunk mode: whether Chunks the ingestion Guardrail scan flags as instructions to an
 * AI are only marked or kept away from Agents. Retrieval follows a change at once.
 */
function FlaggedChunkSetting({
  project,
  organisationId,
}: {
  project: Project;
  organisationId: string;
}) {
  const update = useUpdateProject(organisationId, project.id);
  const archived = project.archived_at !== null;
  // The choice asked for while it saves, shown at once (as the OCR box does).
  const [requested, setRequested] = useState<FlaggedChunkMode | null>(null);
  const shown = requested ?? project.flagged_chunk_mode;
  return (
    <fieldset
      role="radiogroup"
      aria-describedby="flagged-help"
      className="max-w-xl space-y-2 rounded border border-line p-4"
    >
      <legend className="px-1 font-medium">Flagged Chunks</legend>
      <FormError message={projectFailure(update.error)} />
      <p id="flagged-help" className="text-sm text-muted">
        The ingestion scan flags Chunks that look like instructions to an AI, such as text hidden
        in a Document telling the Agent to ignore its rules. Clear a false positive in the
        Document viewer.
      </p>
      {FLAGGED_CHUNK_OPTIONS.map(({ mode, label }) => (
        <label key={mode} className="flex items-center gap-2">
          <input
            type="radio"
            name="flagged-chunk-mode"
            value={mode}
            checked={shown === mode}
            disabled={archived || requested !== null}
            onChange={() => {
              setRequested(mode);
              update.mutate(
                { flagged_chunk_mode: mode },
                {
                  onSettled: () => {
                    setRequested(null);
                  },
                },
              );
            }}
            className="h-4 w-4"
          />
          {label}
        </label>
      ))}
      <p role="status" className="text-sm text-muted">
        {project.flagged_chunk_mode === "exclude"
          ? "Flagged Chunks are never given to an Agent. The Trace lists them as excluded by the ingestion scan."
          : "Flagged Chunks are retrieved like any other, and marked in the Document viewer."}
      </p>
    </fieldset>
  );
}

/** The Project's settings: whether ingestion runs OCR, and what happens to flagged Chunks. */
export function ProjectSettingsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId",
  });
  const project = useProject(organisationId, projectId);
  return (
    <section aria-labelledby="tab-heading" className="space-y-4">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Settings
      </h2>
      {project.data && (
        <>
          <OcrSetting project={project.data} organisationId={organisationId} />
          <FlaggedChunkSetting project={project.data} organisationId={organisationId} />
        </>
      )}
    </section>
  );
}
