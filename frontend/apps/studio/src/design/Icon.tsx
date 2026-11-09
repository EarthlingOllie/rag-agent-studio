/**
 * The Studio's icons: thin-stroke line icons drawn at 24×24 and shown at 16 by default. They are
 * decorative (`aria-hidden`); the control around an icon carries the accessible name.
 */
const PATHS = {
  documents: "M7 3h7l5 5v13H7zM14 3v5h5",
  instructions: "M5 5h14M5 10h14M5 15h9M5 20h6",
  agents: "M12 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM5 21c0-4 3-6 7-6s7 2 7 6",
  profile: "M12 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM5 21c0-4 3-6 7-6s7 2 7 6",
  conversations: "M4 5h16v11H9l-5 4z",
  analytics: "M5 20V10M12 20V4M19 20v-7",
  settings:
    "M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
  projects: "M3 7h7l2 2h9v10H3z",
  security: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  chevronDown: "M7 10l5 5 5-5",
  chevronRight: "M10 7l5 5-5 5",
  chevronLeft: "M14 7l-5 5 5 5",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  search: "M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zM20 20l-4-4",
  upload: "M12 16V4M6 10l6-6 6 6M4 20h16",
  plus: "M12 5v14M5 12h14",
  check: "M5 12l5 5 9-10",
  close: "M6 6l12 12M18 6L6 18",
  warning: "M12 4l9 16H3zM12 10v4M12 17v.01",
  send: "M12 19V5M5 12l7-7 7 7",
  sun: "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
  history: "M4 12a8 8 0 1 0 2.3-5.7M4 4v4h4M12 8v4l3 2",
} as const;

export type IconName = keyof typeof PATHS | "more";

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={name === "more" ? "currentColor" : "none"}
      stroke={name === "more" ? "none" : "currentColor"}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {name === "more" ? (
        <>
          <circle cx="5" cy="12" r="1.7" />
          <circle cx="12" cy="12" r="1.7" />
          <circle cx="19" cy="12" r="1.7" />
        </>
      ) : (
        <path d={PATHS[name]} />
      )}
    </svg>
  );
}

/** The Studio's mark: two waves in the accent colour. */
export function WaveMark({ size = 20 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      className="text-accent"
    >
      <path d="M3 15c3 0 3-3 6-3s3 3 6 3 3-3 6-3" />
      <path d="M3 10c3 0 3-3 6-3s3 3 6 3 3-3 6-3" />
    </svg>
  );
}
