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

/**
 * What happens to Chunks the ingestion Guardrail scan flags as instructions to an AI. There is no
 * choice: they are always quarantined, and only an Editor's review of one Chunk lets it in.
 */
function FlaggedChunksCard() {
  return (
    <section aria-labelledby="flagged-heading" className={CARD}>
      <h3 id="flagged-heading" className={text.subheading}>
        Flagged Chunks
      </h3>
      <p className={text.muted}>
        The ingestion scan flags Chunks that look like instructions to an AI, such as text hidden in a Document telling
        the Agent to ignore its rules.
      </p>
      <p className={text.small}>
        Flagged Chunks are always quarantined: Agents are never given them, and the Trace lists them as excluded by the
        ingestion scan. Review a flagged Chunk in the Document viewer, and allow it there if it is a false positive.
      </p>
    </section>
  );
}

/**
 * The Project's settings, a card each: its Embedding Model (not while archived, when nothing can be
 * re-embedded), whether ingestion runs OCR, and what happens to flagged Chunks (always quarantined). On an archived
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
          <FlaggedChunksCard />
        </div>
      )}
    </section>
  );
}
