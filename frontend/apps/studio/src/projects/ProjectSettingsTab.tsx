import { useParams } from "@tanstack/react-router";

import { FormError } from "../auth/AuthLayout";
import { type Project, projectFailure, useProject, useUpdateProject } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";

function OcrSetting({ project, organisationId }: { project: Project; organisationId: string }) {
  const update = useUpdateProject(organisationId, project.id);
  const archived = project.archived_at !== null;
  return (
    <fieldset className="max-w-xl space-y-2 rounded border border-slate-200 p-4">
      <legend className="px-1 font-medium">OCR</legend>
      <FormError message={projectFailure(update.error)} />
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          // While a change saves (the box is disabled meanwhile), it shows the setting asked for.
          checked={update.isPending ? !project.ocr_enabled : project.ocr_enabled}
          disabled={archived || update.isPending}
          onChange={(event) => {
            update.mutate({ ocr_enabled: event.target.checked });
          }}
          className="h-4 w-4"
        />
        Read scanned PDFs with OCR
      </label>
      <p id="ocr-help" className="text-sm text-slate-700">
        OCR reads text in images, such as scanned pages. It makes processing slower, so leave it off unless this
        Project has scanned PDFs.
      </p>
      <p role="status" className="text-sm text-slate-700">
        {project.ocr_enabled
          ? "OCR is on. New uploads are read with OCR. Retry a Document on the Documents tab to reprocess it."
          : "OCR is off. Text in images isn't read."}
      </p>
    </fieldset>
  );
}

/** The Project's settings: for now, whether ingestion runs OCR. */
export function ProjectSettingsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId" });
  const project = useProject(organisationId, projectId);
  return (
    <section aria-labelledby="tab-heading" className="space-y-4">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Settings
      </h2>
      {project.data && <OcrSetting project={project.data} organisationId={organisationId} />}
    </section>
  );
}
