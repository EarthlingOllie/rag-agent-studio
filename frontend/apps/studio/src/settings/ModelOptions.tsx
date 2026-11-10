import type { ModelInfo } from "./models";

/**
 * A chat model picker's options, grouped by whether each model supports tools: Agentic Retrieval
 * Mode needs a model that does (its Knowledge Search is a tool); one that doesn't can only answer
 * in Automatic mode.
 */
export function ChatModelOptions({ models }: { models: ModelInfo[] }) {
  const groups: [string, ModelInfo[]][] = [
    ["Supports tools: Agentic or Automatic", models.filter((model) => model.supports_tools)],
    ["No tools: Automatic only", models.filter((model) => !model.supports_tools)],
  ];
  return groups
    .filter(([, members]) => members.length > 0)
    .map(([label, members]) => (
      <optgroup key={label} label={label}>
        {members.map((model) => (
          <option key={model.id} value={model.id}>
            {model.name}
          </option>
        ))}
      </optgroup>
    ));
}

/** The chosen model, when it can't use tools. */
export function withoutTools(models: ModelInfo[], id: string): ModelInfo | undefined {
  return models.find((model) => model.id === id && !model.supports_tools);
}
