import { useEffect, useState } from "react";

import { Icon } from "./Icon";
import { button } from "./recipes";

/** How long the button says "Copied". */
export const COPIED_FOR_MS = 2000;

/**
 * Code to paste somewhere else (the Embed snippet, an API call), with a Copy button. Copying
 * changes the button to "Copied" and announces it; if the browser refuses, an alert says how to
 * copy by hand.
 */
export function CodeBlock({ label, code }: { label: string; code: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state !== "copied") return;
    const timer = setTimeout(() => {
      setState("idle");
    }, COPIED_FOR_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [state]);

  return (
    <div className="flex flex-col gap-2">
      <div className="relative rounded-xl border border-line bg-sunken">
        <pre className="overflow-x-auto py-3 pr-28 pl-4 font-mono text-[13px] leading-relaxed text-ink">
          <code>{code}</code>
        </pre>
        <button
          type="button"
          aria-label={`Copy ${label}`}
          className={`${button.secondary} absolute top-2 right-2 h-8 px-3`}
          onClick={() => {
            navigator.clipboard.writeText(code).then(
              () => {
                setState("copied");
              },
              () => {
                setState("failed");
              },
            );
          }}
        >
          <Icon name={state === "copied" ? "check" : "copy"} size={14} />
          {state === "copied" ? "Copied" : "Copy"}
        </button>
      </div>
      <p role="status" className="sr-only">
        {state === "copied" ? `${label} copied.` : ""}
      </p>
      {state === "failed" && (
        <p role="alert" className="text-sm text-danger">
          Couldn&apos;t copy. Select the text and copy it instead.
        </p>
      )}
    </div>
  );
}
