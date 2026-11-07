import { MarkdownEditor } from "@studio/ui";
import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";

import { type Capability, type Credential, useCredentials } from "../settings/credentials";
import { type Agent, StaleDraftError, useSaveDraft, useStoreAgent } from "./agents";
import { type Draft, DraftRequestError, errorsFor, type FieldError, type ModelChoice, useCredentialModels } from "./draft";
import { INPUT } from "./ProjectsPage";
import { useTags } from "./tags";

/** How long typing must pause before the Draft is saved. */
export const AUTOSAVE_MS = 600;

const PROVIDER_NAMES: Record<Credential["provider"], string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  bedrock: "Amazon Bedrock",
  voyage: "Voyage AI",
  // The seeded demo provider: canned answers from the Knowledge Base, never a real model.
  demo: "Demo: canned answers, not a real model",
};

type Status = "saved" | "dirty" | "saving" | "invalid" | "failed" | "conflict";

const FAILED_TEXT = "something went wrong. Your next change tries again.";

const STATUS_TEXT: Record<Exclude<Status, "failed">, string> = {
  conflict: "Not saved: someone else changed this Draft.",
  saved: "All changes saved",
  dirty: "Unsaved changes",
  saving: "Saving…",
  invalid: "Not saved: fix the settings marked below.",
};

const ERROR_TEXT = "mt-1 text-sm text-red-800";

/** The messages for one setting, linked to its control by `id`. */
function Errors({ id, messages }: { id: string; messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <p id={id} className={ERROR_TEXT}>
      {messages.join(" ")}
    </p>
  );
}

type FieldProps = {
  label: string;
  hint?: string | undefined;
  errors: string[];
  children: (control: ControlProps) => ReactNode;
};
type ControlProps = {
  id: string;
  "aria-invalid": true | undefined;
  "aria-describedby": string | undefined;
  className: string;
};

/** A labelled control with its hint and the reasons it was refused. */
function Field({ label, hint, errors, children }: FieldProps) {
  const id = useId();
  const described = [hint && `${id}-hint`, errors.length > 0 && `${id}-error`].filter(Boolean).join(" ");
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-slate-700">
          {hint}
        </p>
      )}
      {children({
        id,
        "aria-invalid": errors.length > 0 ? true : undefined,
        "aria-describedby": described || undefined,
        className: INPUT,
      })}
      <Errors id={`${id}-error`} messages={errors} />
    </div>
  );
}

/** A number setting. It keeps what was typed, so a half-typed number isn't rewritten. */
function NumberField({
  label,
  hint,
  errors,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  hint?: string | undefined;
  errors: string[];
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  const [text, setText] = useState(String(value));
  return (
    <Field label={label} hint={hint} errors={errors}>
      {(control) => (
        <input
          {...control}
          className={`${control.className} w-32`}
          type="number"
          min={min}
          max={max}
          step={step}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            onChange(event.target.value === "" ? Number.NaN : Number(event.target.value));
          }}
        />
      )}
    </Field>
  );
}

function TextField({
  label,
  hint,
  errors,
  value,
  onChange,
  rows,
}: {
  label: string;
  hint?: string | undefined;
  errors: string[];
  value: string;
  onChange: (value: string) => void;
  rows?: number;
}) {
  return (
    <Field label={label} hint={hint} errors={errors}>
      {(control) =>
        rows ? (
          <textarea
            {...control}
            rows={rows}
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
            }}
          />
        ) : (
          <input
            {...control}
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
            }}
          />
        )
      }
    </Field>
  );
}

/** A select of fixed options. */
function ChoiceField<Value extends string>({
  label,
  hint,
  errors,
  value,
  options,
  onChange,
}: {
  label: string;
  hint?: string | undefined;
  errors: string[];
  value: Value;
  options: [Value, string][];
  onChange: (value: Value) => void;
}) {
  return (
    <Field label={label} hint={hint} errors={errors}>
      {(control) => (
        <select
          {...control}
          value={value}
          onChange={(event) => {
            onChange(event.target.value as Value);
          }}
        >
          {options.map(([option, name]) => (
            <option key={option} value={option}>
              {name}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

/**
 * A Provider Credential with the capability, then one of its models. Choosing a credential asks
 * for a model; the setting changes once one is chosen. "None" clears it.
 */
function ModelChoiceField({
  legend,
  noneLabel,
  hint,
  empty,
  capability,
  organisationId,
  value,
  errors,
  field,
  onChange,
  onIncomplete,
}: {
  field: string;
  legend: string;
  noneLabel: string;
  hint: string;
  empty: string;
  capability: Capability;
  organisationId: string;
  value: ModelChoice | null;
  errors: string[];
  onChange: (value: ModelChoice | null) => void;
  /** Whether a credential is chosen that differs from the saved one and still waits for a model. */
  onIncomplete: (field: string, incomplete: boolean) => void;
}) {
  const id = useId();
  const credentials = useCredentials(organisationId);
  const [credentialId, setCredentialId] = useState(value?.credential_id ?? "");
  const models = useCredentialModels(organisationId, credentialId, capability);
  const offering = (credentials.data ?? [])
    .filter((credential) => credential.capabilities.includes(capability))
    .sort((a, b) => a.name.localeCompare(b.name));
  const options = models.data ?? [];
  const model = value?.credential_id === credentialId ? value.model : "";
  const incomplete = credentialId !== "" && value?.credential_id !== credentialId;
  useEffect(() => {
    onIncomplete(field, incomplete);
  }, [field, incomplete, onIncomplete]);
  return (
    <fieldset className="space-y-2 rounded border border-slate-200 p-3">
      <legend className="px-1 text-sm font-medium">{legend}</legend>
      <p className="text-xs text-slate-700">{hint}</p>
      {credentials.isSuccess && offering.length === 0 && !value ? (
        <p className="text-sm text-slate-700">{empty}</p>
      ) : (
        <>
          <label htmlFor={`${id}-credential`} className="block text-sm">
            Credential
          </label>
          <select
            id={`${id}-credential`}
            className={INPUT}
            value={credentialId}
            onChange={(event) => {
              setCredentialId(event.target.value);
              if (event.target.value === "") onChange(null);
            }}
          >
            <option value="">{noneLabel}</option>
            {offering.map((credential) => (
              <option key={credential.id} value={credential.id}>
                {`${credential.name} (${PROVIDER_NAMES[credential.provider]})`}
              </option>
            ))}
          </select>
          {credentialId !== "" &&
            (!models.isPending && options.length === 0 ? (
              <p className="text-sm text-slate-700">This credential offers no models for this.</p>
            ) : (
              <>
                <label htmlFor={`${id}-model`} className="block text-sm">
                  Model
                </label>
                <select
                  id={`${id}-model`}
                  className={INPUT}
                  value={model}
                  onChange={(event) => {
                    onChange({
                      credential_id: credentialId,
                      model: event.target.value,
                    });
                  }}
                >
                  <option value="" disabled>
                    Choose a model…
                  </option>
                  {options.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
                {incomplete && <p className="text-sm text-slate-700">Choose a model to use this credential.</p>}
              </>
            ))}
        </>
      )}
      <Errors id={`${id}-error`} messages={errors} />
    </fieldset>
  );
}

function TagScoping({
  organisationId,
  projectId,
  value,
  errors,
  onChange,
}: {
  organisationId: string;
  projectId: string;
  value: string[];
  errors: string[];
  onChange: (value: string[]) => void;
}) {
  const tags = useTags(organisationId, projectId);
  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium">Tag scoping</legend>
      <p className="text-xs text-slate-700">Only search Documents with one of these Tags. None searches every Document.</p>
      {tags.data?.length === 0 && <p className="text-sm text-slate-700">This Project has no Tags yet.</p>}
      {(tags.data ?? []).map((tag) => (
        <label key={tag.id} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.includes(tag.id)}
            onChange={(event) => {
              onChange(event.target.checked ? [...value, tag.id] : value.filter((id) => id !== tag.id));
            }}
          />
          {tag.name}
        </label>
      ))}
      <Errors id="tag-scoping-error" messages={errors} />
    </fieldset>
  );
}

/** A group of settings; disabling it disables every control in it. */
function Group({ legend, disabled, children }: { legend: string; disabled: boolean; children: ReactNode }) {
  return (
    <fieldset disabled={disabled} className="space-y-3 rounded border border-slate-300 p-4">
      <legend className="px-1 text-base font-semibold">{legend}</legend>
      {children}
    </fieldset>
  );
}

/** Settings that can't be sent at all: numbers left empty. */
function localErrors(draft: Draft): FieldError[] {
  const numbers: [string, number][] = [
    ["behaviour.temperature", draft.behaviour.temperature],
    ["behaviour.max_output_tokens", draft.behaviour.max_output_tokens],
    ["behaviour.remembered_turns", draft.behaviour.remembered_turns],
    ["retrieval.top_k", draft.retrieval.top_k],
    ["retrieval.hybrid_weight", draft.retrieval.hybrid_weight],
    ["retrieval.min_score", draft.retrieval.min_score],
    ["experience.rating_prompt_after", draft.experience.rating_prompt_after],
  ];
  return numbers.filter(([, value]) => Number.isNaN(value)).map(([field]) => ({ field, message: "Enter a number." }));
}

const orNull = (text: string) => (text.trim() === "" ? null : text);

/**
 * Someone else saved the Draft after the revision these edits were made on: the Editor loads
 * their Draft (losing these edits) or saves these edits over theirs.
 */
function DraftConflict({ latest, onLoad, onKeep }: { latest: Agent; onLoad: () => void; onKeep: () => void }) {
  return (
    <div role="alert" className="space-y-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
      <p>
        Someone else saved this Draft while you were editing (saved {new Date(latest.draft_updated_at).toLocaleString()}). Your
        changes aren&apos;t saved. Load their Draft, or save yours over it.
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={CONFLICT_BUTTON} onClick={onLoad}>
          Load their changes
        </button>
        <button type="button" className={CONFLICT_BUTTON} onClick={onKeep}>
          Save mine over theirs
        </button>
      </div>
    </div>
  );
}

const CONFLICT_BUTTON = "rounded border border-slate-400 bg-white px-3 py-1 text-sm text-slate-900 hover:bg-slate-100";

/**
 * The Agent's Draft, every group of its AgentConfig. Each change is saved automatically once
 * typing pauses; the status says whether everything is saved, and the API's reasons for
 * refusing a setting appear beside it. Saves name the Draft revision they were made on; when
 * someone else has saved since, the Editor is asked to load their Draft or save their own over it,
 * and `onReplaced` is called once the Draft is replaced so the editor starts again from it.
 */
export function DraftEditor({ agent, organisationId, onReplaced }: { agent: Agent; organisationId: string; onReplaced: () => void }) {
  // An archived Agent's Draft can't change until an Owner restores it.
  const readOnly = agent.archived_at !== null;
  const save = useSaveDraft(organisationId, agent.project_id, agent.id);
  const [draft, setDraft] = useState<Draft>(agent.draft);
  const [status, setStatus] = useState<Status>("saved");
  const [failure, setFailure] = useState<string>("");
  const [errors, setErrors] = useState<FieldError[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  // Only the latest change's save decides the status.
  const latest = useRef(0);
  // A change waiting for typing to pause; saved at once if the editor closes first.
  const waiting = useRef<Draft | null>(null);
  // Saves run one at a time, in order, so an older save can never land after a newer one.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  // The newest change handed to the queue; an older queued save that hasn't started is skipped.
  const queued = useRef(0);
  // Pickers with a credential chosen but no model yet: a change not yet in the Draft.
  const [incomplete, setIncomplete] = useState<Record<string, boolean>>({});
  const { mutateAsync } = save;
  const store = useStoreAgent(organisationId, agent.project_id);
  // The Draft revision these edits are made on: the last one this editor saved or loaded.
  const base = useRef(agent.draft_revision);
  // Someone else's Draft, when a save was refused because they had saved since.
  const [conflict, setConflict] = useState<Agent | null>(null);

  const enqueue = useCallback(
    (next: Draft, version: number) => {
      queued.current = version;
      queue.current = queue.current.then(async () => {
        if (version !== queued.current) return;
        try {
          const saved = await mutateAsync({ draft: next, baseRevision: base.current });
          base.current = saved.draft_revision;
          if (version !== latest.current) return;
          setErrors([]);
          setStatus("saved");
        } catch (error) {
          if (error instanceof StaleDraftError) {
            setConflict(error.latest);
            setStatus("conflict");
            return;
          }
          if (version !== latest.current) return;
          const fields = error instanceof DraftRequestError ? error.fields : [];
          setErrors(fields);
          if (fields.length > 0) {
            setStatus("invalid");
          } else {
            setFailure((error instanceof DraftRequestError && error.detail) || FAILED_TEXT);
            setStatus("failed");
          }
        }
      });
    },
    [mutateAsync],
  );

  useEffect(
    () => () => {
      clearTimeout(timer.current);
      if (waiting.current) enqueue(waiting.current, latest.current);
    },
    [enqueue],
  );

  const reportIncomplete = useCallback((field: string, value: boolean) => {
    setIncomplete((current) => ({ ...current, [field]: value }));
  }, []);
  const awaitingModel = Object.values(incomplete).some(Boolean);

  function change(next: Draft) {
    setDraft(next);
    clearTimeout(timer.current);
    waiting.current = null;
    const version = ++latest.current;
    const local = localErrors(next);
    if (local.length > 0) {
      setErrors(local);
      setStatus("invalid");
      return;
    }
    setStatus("dirty");
    waiting.current = next;
    timer.current = setTimeout(() => {
      waiting.current = null;
      setStatus("saving");
      enqueue(next, version);
    }, AUTOSAVE_MS);
  }

  const { behaviour, retrieval, experience, guardrails } = draft;
  const setBehaviour = (update: Partial<Draft["behaviour"]>) => {
    change({ ...draft, behaviour: { ...behaviour, ...update } });
  };
  const setRetrieval = (update: Partial<Draft["retrieval"]>) => {
    change({ ...draft, retrieval: { ...retrieval, ...update } });
  };
  const setExperience = (update: Partial<Draft["experience"]>) => {
    change({ ...draft, experience: { ...experience, ...update } });
  };
  const setUiText = (update: Partial<Draft["experience"]["ui_text"]>) => {
    setExperience({ ui_text: { ...experience.ui_text, ...update } });
  };
  const setGuardrails = (update: Partial<Draft["guardrails"]>) => {
    change({ ...draft, guardrails: { ...guardrails, ...update } });
  };
  const at = (field: string) => errorsFor(errors, field);
  const systemPromptErrorId = useId();
  const [questions, setQuestions] = useState(experience.starter_questions.join("\n"));

  return (
    // No submit button: changes save themselves.
    <form aria-labelledby="draft-heading" className="space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="draft-heading" className="text-lg font-semibold">
          Draft
        </h2>
        <p role="status" aria-label="Draft status" className={`text-sm ${status === "saved" ? "text-slate-700" : "text-slate-900"}`}>
          {readOnly
            ? "Read only while archived."
            : status === "failed"
              ? `Not saved: ${failure}`
              : awaitingModel && (status === "saved" || status === "saving")
                ? "Unsaved changes: choose a model."
                : STATUS_TEXT[status]}
        </p>
      </div>
      {conflict && (
        <DraftConflict
          latest={conflict}
          onLoad={() => {
            void store(conflict);
            onReplaced();
          }}
          onKeep={() => {
            base.current = conflict.draft_revision;
            setConflict(null);
            setStatus("saving");
            enqueue(draft, ++latest.current);
          }}
        />
      )}

      <Group legend="Behaviour" disabled={readOnly}>
        <div>
          {/* Written and stored as markdown (ticket 04-02). */}
          <MarkdownEditor
            label="System prompt"
            maxLength={20000}
            disabled={readOnly}
            defaultValue={behaviour.system_prompt}
            onChange={(system_prompt) => {
              setBehaviour({ system_prompt });
            }}
          />
          <Errors id={systemPromptErrorId} messages={at("behaviour.system_prompt")} />
        </div>
        <ModelChoiceField
          legend="Model override"
          noneLabel="None: use the Default Model"
          hint="Answer with a model of a chat credential instead of the Organisation's Default Model."
          empty="No credential can be used for chat yet. The Default Model answers."
          capability="chat"
          organisationId={organisationId}
          value={behaviour.model}
          errors={at("behaviour.model")}
          field="behaviour.model"
          onIncomplete={reportIncomplete}
          onChange={(model) => {
            setBehaviour({ model });
          }}
        />
        <NumberField
          label="Temperature"
          hint="0 is focused and repeatable, 1 more varied."
          min={0}
          max={1}
          step={0.1}
          errors={at("behaviour.temperature")}
          value={behaviour.temperature}
          onChange={(temperature) => {
            setBehaviour({ temperature });
          }}
        />
        <NumberField
          label="Max output tokens"
          min={1}
          max={8192}
          errors={at("behaviour.max_output_tokens")}
          value={behaviour.max_output_tokens}
          onChange={(max_output_tokens) => {
            setBehaviour({ max_output_tokens });
          }}
        />
        <NumberField
          label="Remembered turns"
          hint="How many earlier questions and answers the model sees."
          min={0}
          max={20}
          errors={at("behaviour.remembered_turns")}
          value={behaviour.remembered_turns}
          onChange={(remembered_turns) => {
            setBehaviour({ remembered_turns });
          }}
        />
        <TextField
          label="Fallback text (when nothing relevant is found)"
          rows={2}
          errors={at("behaviour.fallback_text")}
          value={behaviour.fallback_text}
          onChange={(fallback_text) => {
            setBehaviour({ fallback_text });
          }}
        />
      </Group>

      <Group legend="Retrieval" disabled={readOnly}>
        <NumberField
          label="Chunks per answer (top-k)"
          min={1}
          max={20}
          errors={at("retrieval.top_k")}
          value={retrieval.top_k}
          onChange={(top_k) => {
            setRetrieval({ top_k });
          }}
        />
        <NumberField
          label="Hybrid weighting (1 semantic only, 0 keyword only)"
          min={0}
          max={1}
          step={0.1}
          errors={at("retrieval.hybrid_weight")}
          value={retrieval.hybrid_weight}
          onChange={(hybrid_weight) => {
            setRetrieval({ hybrid_weight });
          }}
        />
        <NumberField
          label="Minimum relevance (0 to 1)"
          min={0}
          max={1}
          step={0.05}
          errors={at("retrieval.min_score")}
          value={retrieval.min_score}
          onChange={(min_score) => {
            setRetrieval({ min_score });
          }}
        />
        <TagScoping
          organisationId={organisationId}
          projectId={agent.project_id}
          value={retrieval.tag_ids}
          errors={at("retrieval.tag_ids")}
          onChange={(tag_ids) => {
            setRetrieval({ tag_ids });
          }}
        />
        <ModelChoiceField
          legend="Reranker"
          noneLabel="None"
          hint="Reorder the retrieved Chunks with a rerank model before the best are chosen."
          empty="No credential can rerank yet. Add a Voyage or Bedrock credential with reranking."
          capability="rerank"
          organisationId={organisationId}
          value={retrieval.reranker}
          errors={at("retrieval.reranker")}
          field="retrieval.reranker"
          onIncomplete={reportIncomplete}
          onChange={(reranker) => {
            setRetrieval({ reranker });
          }}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={retrieval.citations}
            onChange={(event) => {
              setRetrieval({ citations: event.target.checked });
            }}
          />
          Show citations to Visitors
        </label>
      </Group>

      <Group legend="Experience" disabled={readOnly}>
        <TextField
          label="Display name"
          hint={`Empty shows the Agent's name, ${agent.name}.`}
          errors={at("experience.display_name")}
          value={experience.display_name}
          onChange={(display_name) => {
            setExperience({ display_name });
          }}
        />
        <TextField
          label="Avatar URL (https)"
          errors={at("experience.avatar_url")}
          value={experience.avatar_url ?? ""}
          onChange={(avatar_url) => {
            setExperience({ avatar_url: orNull(avatar_url) });
          }}
        />
        <TextField
          label="Greeting"
          rows={2}
          errors={at("experience.greeting")}
          value={experience.greeting}
          onChange={(greeting) => {
            setExperience({ greeting });
          }}
        />
        <TextField
          label="Starter questions (one per line, up to 6)"
          rows={4}
          errors={at("experience.starter_questions")}
          value={questions}
          onChange={(typed) => {
            setQuestions(typed);
            const lines = typed.split("\n").map((line) => line.trim());
            setExperience({
              starter_questions: lines.filter((line) => line !== ""),
            });
          }}
        />
        <TextField
          label='"Send" button text'
          hint="Empty keeps the built-in text."
          errors={at("experience.ui_text.send_button")}
          value={experience.ui_text.send_button ?? ""}
          onChange={(text) => {
            setUiText({ send_button: orNull(text) });
          }}
        />
        <TextField
          label='"Rate this conversation" text'
          errors={at("experience.ui_text.rate_conversation")}
          value={experience.ui_text.rate_conversation ?? ""}
          onChange={(text) => {
            setUiText({ rate_conversation: orNull(text) });
          }}
        />
        <TextField
          label="Unavailable message"
          errors={at("experience.ui_text.unavailable_message")}
          value={experience.ui_text.unavailable_message ?? ""}
          onChange={(text) => {
            setUiText({ unavailable_message: orNull(text) });
          }}
        />
        <NumberField
          label="Rating prompt after this many replies (0: only at the end)"
          min={0}
          max={50}
          errors={at("experience.rating_prompt_after")}
          value={experience.rating_prompt_after}
          onChange={(rating_prompt_after) => {
            setExperience({ rating_prompt_after });
          }}
        />
      </Group>

      <Group legend="Guardrails" disabled={readOnly}>
        <p className="text-sm text-slate-700">
          Every message is checked by the built-in classifier. Block mode and the LLM classifier
          are enforced; warn and log are saved with the Draft and enforced in a later release.
        </p>
        <ChoiceField
          label="Input Guardrail mode"
          errors={at("guardrails.input_mode")}
          value={guardrails.input_mode}
          options={[
            ["block", "Block: refuse the message"],
            ["warn", "Warn: answer with a caution"],
            ["log", "Log: only record the verdict"],
          ]}
          onChange={(input_mode) => {
            setGuardrails({ input_mode });
          }}
        />
        <ModelChoiceField
          legend="LLM classifier"
          noneLabel="None"
          hint="Also check each message with a chat model, in addition to the built-in classifier."
          empty="No credential can be used for chat yet."
          capability="chat"
          organisationId={organisationId}
          value={guardrails.classifier}
          errors={at("guardrails.classifier")}
          field="guardrails.classifier"
          onIncomplete={reportIncomplete}
          onChange={(classifier) => {
            setGuardrails({ classifier });
          }}
        />
        <ChoiceField
          label="When the classifier errors"
          errors={at("guardrails.fail_mode")}
          value={guardrails.fail_mode}
          options={[
            ["closed", "Fail closed: treat the message as flagged"],
            ["open", "Fail open: let the message through"],
          ]}
          onChange={(fail_mode) => {
            setGuardrails({ fail_mode });
          }}
        />
        <TextField
          label="Refusal text"
          rows={2}
          errors={at("guardrails.refusal_text")}
          value={guardrails.refusal_text}
          onChange={(refusal_text) => {
            setGuardrails({ refusal_text });
          }}
        />
      </Group>
    </form>
  );
}
