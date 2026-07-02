"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Counts a numeric value up to its target on mount and whenever the value
 * changes. Honors prefers-reduced-motion (snaps instantly). `format` maps the
 * interpolated number to the display string so callers keep currency/percent
 * formatting.
 */
export function AnimatedNumber({
  value,
  format,
  durationMs = 650,
  className = "",
}: {
  value: number | null | undefined;
  format: (n: number) => string;
  durationMs?: number;
  className?: string;
}) {
  const [display, setDisplay] = useState<number>(value ?? 0);
  const fromRef = useRef<number>(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (value == null || isNaN(value)) {
      setDisplay(0);
      return;
    }
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setDisplay(value);
      return;
    }

    const from = fromRef.current;
    const to = value;
    const start = performance.now();

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      const current = from + (to - from) * eased;
      setDisplay(current);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      fromRef.current = value;
    };
  }, [value, durationMs]);

  if (value == null || isNaN(value)) return <span className={className}>—</span>;
  return <span className={className}>{format(display)}</span>;
}
