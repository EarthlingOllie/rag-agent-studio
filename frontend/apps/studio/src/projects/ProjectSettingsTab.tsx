import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { field, layout, PageHeader, surface, text } from "../design";
import { EmbeddingModelSetting } from "./EmbeddingModel";
import {
  type Project,
  projectFailure,
  useProject,
  useUpdateProject,
} from "./projects";
import { useOrganisationRole } from "./ProjectsPage";

/** A setting's card: a titled panel, its explanation, then its control. */
const CARD = `${surface.panel} flex flex-col gap-3`;

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
    <section aria-labelledby="ocr-heading" className={CARD}>
      <h3 id="ocr-heading" className={text.subheading}>
        OCR
      </h3>
      <p id="ocr-help" className={text.muted}>
        OCR reads text in images, such as scanned pages. It makes processing
        slower, so leave it off unless this Project has scanned PDFs.
      </p>
      <FormError message={projectFailure(update.error)} />
      <label className="flex items-center justify-between gap-4 rounded-xl bg-sunken px-3.5 py-3 has-disabled:opacity-60">
        <span className="text-sm font-medium text-ink">Read scanned PDFs with OCR</span>
        <input
          type="checkbox"
          aria-describedby="ocr-help"
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
          className={field.checkbox}
        />
      </label>
      <p role="status" className={text.small}>
        {project.ocr_enabled
          ? "OCR is on. New uploads are read with OCR. Retry a Document on the Documents tab to reprocess it."
          : "OCR is off. Text in images isn't read."}
      </p>
    </section>
  );
}

type FlaggedChunkMode = Project["flagged_chunk_mode"];

const FLAGGED_CHUNK_OPTIONS: { mode: FlaggedChunkMode; label: string; description: string }[] = [
  {
    mode: "mark",
    label: "Mark them, and keep retrieving them",
    description: "Agents can still be given them. The Document viewer marks them for review.",
  },
  {
    mode: "exclude",
    label: "Exclude them from retrieval",
    description: "Agents are never given them. The Trace lists them as excluded.",
  },
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
    <section aria-labelledby="flagged-heading" className={CARD}>
      <h3 id="flagged-heading" className={text.subheading}>
        Flagged Chunks
      </h3>
      <p id="flagged-help" className={text.muted}>
        The ingestion scan flags Chunks that look like instructions to an AI, such as text hidden
        in a Document telling the Agent to ignore its rules. Clear a false positive in the
        Document viewer.
      </p>
      <fieldset
        role="radiogroup"
        aria-labelledby="flagged-heading"
        aria-describedby="flagged-help"
        className="flex flex-col gap-3"
      >
        <FormError message={projectFailure(update.error)} />
        <div className="grid gap-3 sm:grid-cols-2">
          {FLAGGED_CHUNK_OPTIONS.map(({ mode, label, description }) => (
            <label
              key={mode}
              className="flex cursor-pointer items-start gap-3 rounded-xl border border-line px-3.5 py-3 has-checked:border-accent has-checked:bg-accent-soft has-disabled:cursor-not-allowed has-disabled:opacity-60"
            >
              <input
                type="radio"
                name="flagged-chunk-mode"
                value={mode}
                aria-labelledby={`flagged-${mode}-label`}
                aria-describedby={`flagged-${mode}-description`}
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
                className={`${field.checkbox} mt-0.5 shrink-0`}
              />
              <span className="flex flex-col gap-0.5">
                <span id={`flagged-${mode}-label`} className="text-sm font-medium text-ink">
                  {label}
                </span>
                <span id={`flagged-${mode}-description`} className={text.small}>
                  {description}
                </span>
              </span>
            </label>
          ))}
        </div>
        <p role="status" className={text.small}>
          {project.flagged_chunk_mode === "exclude"
            ? "Flagged Chunks are never given to an Agent. The Trace lists them as excluded by the ingestion scan."
            : "Flagged Chunks are retrieved like any other, and marked in the Document viewer."}
        </p>
      </fieldset>
    </section>
  );
}

/**
 * The Project's settings, a card each: its Embedding Model (not while archived, when nothing can be
 * re-embedded), whether ingestion runs OCR, and what happens to flagged Chunks. On an archived
 * Project they are shown disabled.
 */
export function ProjectSettingsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId",
  });
  const project = useProject(organisationId, projectId);
  const archived = project.data?.archived_at != null;
  return (
    <section aria-label="Settings" className={layout.stack}>
      <PageHeader
        level={2}
        title="Settings"
        description={
          archived
            ? "This Project is archived, so its settings can't be changed."
            : "How this Project embeds, reads and screens its Documents. A change applies to every Agent in it."
        }
      />
      {project.data && (
        <div className="grid max-w-2xl gap-6">
          {!archived && <EmbeddingModelSetting project={project.data} organisationId={organisationId} />}
          <OcrSetting project={project.data} organisationId={organisationId} />
          <FlaggedChunkSetting project={project.data} organisationId={organisationId} />
        </div>
      )}
    </section>
  );
}
