/** From this share of the limit the meter turns to the warning colour. */
const NEAR = 0.8;

/**
 * How much of a limit is used (Token Budget, quota). The fill is the accent under 80%, the flag
 * colour from 80% and the danger colour once spent; the value is always printed beside it, so
 * the colour is never the only signal. A `progress` meter (a re-embed's Chunks) has no limit to
 * warn about, so it stays the accent all the way.
 */
export function Meter({
  label,
  value,
  max,
  unit,
  format = (n) => n.toLocaleString("en-GB"),
  progress = false,
}: {
  label: string;
  value: number;
  /** The limit; more than zero. */
  max: number;
  /** Said after the numbers: "tokens". */
  unit?: string;
  format?: (n: number) => string;
  /** How far work has got rather than how much of a limit is used: never the warning colours. */
  progress?: boolean;
}) {
  const share = value / max;
  const tone = progress ? "bg-accent" : share >= 1 ? "bg-danger" : share >= NEAR ? "bg-flag" : "bg-accent";
  const suffix = unit === undefined ? "" : ` ${unit}`;
  return (
    <div className="flex items-center gap-3">
      <div
        role="meter"
        aria-label={label}
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuetext={`${format(value)} of ${format(max)}${suffix}`}
        className="h-2 flex-1 overflow-hidden rounded-full bg-sunken"
      >
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${String(Math.min(share, 1) * 100)}%` }} />
      </div>
      <span className="font-mono text-[13px] whitespace-nowrap text-ink-2">
        {format(value)} / {format(max)}
        {suffix}
      </span>
    </div>
  );
}
