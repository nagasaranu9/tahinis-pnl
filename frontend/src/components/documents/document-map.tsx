"use client";

import Link from "next/link";
import { CheckCircle2, MinusCircle } from "lucide-react";
import { useDocumentSummaryMap, type DocMapBucket } from "@/hooks/use-documents";

function money(v: string) {
  return parseFloat(v).toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 });
}

// Deep-link each bucket to its filtered documents view.
function href(type: string) {
  if (type === "duplicate") return "/documents";
  return `/documents?type=${type}`;
}

function Row({ b, counted }: { b: DocMapBucket; counted: boolean }) {
  return (
    <Link
      href={href(b.type)}
      className="flex items-center justify-between gap-2 px-3 py-2 rounded-md hover:bg-muted/50 transition-colors text-sm"
    >
      <span className="min-w-0 truncate">{b.label}</span>
      <span className="flex items-center gap-2 shrink-0">
        <span className="text-muted-foreground tabular-nums">{b.count}</span>
        <span className={`tabular-nums ${counted ? "font-medium" : "text-muted-foreground line-through"}`}>
          {money(b.total)}
        </span>
      </span>
    </Link>
  );
}

export function DocumentMap() {
  const { data, isLoading } = useDocumentSummaryMap();
  if (isLoading || !data) return null;

  return (
    <div className="grid md:grid-cols-2 gap-3 mb-6">
      {/* Counted */}
      <div className="rounded-xl border border-green-500/30 bg-green-500/[0.03] p-3">
        <div className="flex items-center justify-between px-1 mb-1.5">
          <p className="text-sm font-medium flex items-center gap-1.5">
            <CheckCircle2 className="h-4 w-4 text-green-600" /> Counted in P&amp;L
          </p>
          <p className="text-sm font-semibold tabular-nums">{money(data.counted_total)}</p>
        </div>
        <div className="space-y-0.5">
          {data.counted.map((b) => <Row key={b.type} b={b} counted />)}
          {data.counted.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">Nothing yet.</p>}
        </div>
      </div>

      {/* Excluded */}
      <div className="rounded-xl border border-border bg-muted/20 p-3">
        <div className="flex items-center justify-between px-1 mb-1.5">
          <p className="text-sm font-medium flex items-center gap-1.5 text-muted-foreground">
            <MinusCircle className="h-4 w-4" /> Recorded, not counted
          </p>
        </div>
        <div className="space-y-0.5">
          {data.excluded.map((b) => <Row key={b.type} b={b} counted={false} />)}
          {data.excluded.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">None.</p>}
        </div>
        <p className="px-3 pt-2 text-xs text-muted-foreground">
          Payment receipts, payroll &amp; duplicates — kept as proof, excluded to avoid double-counting.
        </p>
      </div>
    </div>
  );
}
