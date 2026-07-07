"use client";

/**
 * Brand loading indicator — the Tahini's flame logo with a flame-flicker
 * animation (see .flame-flicker in globals.css). Respects prefers-reduced-motion
 * (falls back to a gentle opacity pulse).
 *
 * Usage:
 *   {isLoading ? <FlameLoader /> : <Data />}
 *   <FlameLoader size="sm" label="Loading reviews…" />
 *   <FullPageFlameLoader />   // centered, fills its container
 */
const SIZES = { sm: 24, md: 40, lg: 64, xl: 96 } as const;

export function FlameLoader({
  size = "md",
  label,
  className = "",
}: {
  size?: keyof typeof SIZES;
  label?: string;
  className?: string;
}) {
  const px = SIZES[size];
  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 ${className}`}
      role="status"
      aria-live="polite"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/tahinis-icon.png"
        alt=""
        width={px}
        height={px}
        className="flame-flicker select-none"
        style={{ width: px, height: px }}
        draggable={false}
      />
      {label ? (
        <span className="text-xs text-muted-foreground">{label}</span>
      ) : (
        <span className="sr-only">Loading…</span>
      )}
    </div>
  );
}

/** Centered loader that fills its parent (min-height 12rem) — for page/section loads. */
export function FullPageFlameLoader({ label }: { label?: string }) {
  return (
    <div className="flex min-h-[12rem] w-full items-center justify-center">
      <FlameLoader size="lg" label={label} />
    </div>
  );
}
