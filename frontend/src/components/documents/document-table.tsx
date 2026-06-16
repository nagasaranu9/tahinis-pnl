"use client";

import Link from "next/link";
import { format, parseISO } from "date-fns";
import { FileText, ExternalLink, Copy } from "lucide-react";
import { DocumentStatusBadge } from "./document-status-badge";
import type { Document } from "@/types/document";

interface Props {
  documents: Document[];
}

function formatCurrency(amount: string | null, currency: string): string {
  if (!amount) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(parseFloat(amount));
}

function getGroupKey(doc: Document): string {
  const dateStr = doc.document_date ?? doc.created_at;
  if (!dateStr) return "Unknown Date";
  try {
    return format(parseISO(dateStr), "MMMM yyyy");
  } catch {
    return "Unknown Date";
  }
}

function getSortDate(doc: Document): number {
  const dateStr = doc.document_date ?? doc.created_at;
  if (!dateStr) return 0;
  try {
    return parseISO(dateStr).getTime();
  } catch {
    return 0;
  }
}

export function DocumentTable({ documents }: Props) {
  if (documents.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <FileText className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">No documents yet. Upload an invoice or receipt above.</p>
      </div>
    );
  }

  // Group by month/year, newest first
  const grouped = new Map<string, Document[]>();
  const groupOrder: string[] = [];

  const sorted = [...documents].sort((a, b) => getSortDate(b) - getSortDate(a));
  for (const doc of sorted) {
    const key = getGroupKey(doc);
    if (!grouped.has(key)) {
      grouped.set(key, []);
      groupOrder.push(key);
    }
    grouped.get(key)!.push(doc);
  }

  return (
    <div className="space-y-6">
      {groupOrder.map((monthYear) => (
        <div key={monthYear}>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 px-1">
            {monthYear}
          </h3>
          <div className="rounded-lg border border-border overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">File</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Vendor</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Type</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Date</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Amount</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Status</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {grouped.get(monthYear)!.map((doc) => (
                  <tr key={doc.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-primary/60 shrink-0" />
                        <span className="truncate max-w-[200px]" title={doc.original_filename}>
                          {doc.original_filename}
                        </span>
                        {doc.is_duplicate && (
                          <span
                            title="Duplicate — already imported from another source"
                            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-orange-500/10 text-orange-500 border border-orange-500/20 shrink-0"
                          >
                            <Copy className="h-2.5 w-2.5" />
                            DUPLICATE
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {doc.vendor_name ?? "—"}
                    </td>
                    <td className="px-4 py-3 capitalize text-muted-foreground">
                      {doc.document_type}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {doc.document_date
                        ? format(parseISO(doc.document_date), "MMM d, yyyy")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-medium">
                      {formatCurrency(doc.total_amount, doc.currency_code)}
                    </td>
                    <td className="px-4 py-3">
                      <DocumentStatusBadge status={doc.status} />
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/documents/${doc.id}`}
                        className="text-primary hover:underline flex items-center gap-1"
                      >
                        <ExternalLink className="h-3 w-3" />
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
