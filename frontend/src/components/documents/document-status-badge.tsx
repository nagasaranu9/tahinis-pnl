import { cn } from "@/lib/utils";
import type { DocumentStatus } from "@/types/document";

const STATUS_CONFIG: Record<DocumentStatus, { label: string; className: string }> = {
  pending:        { label: "Pending",       className: "bg-yellow-500/10 text-yellow-400" },
  ocr_processing: { label: "Processing",    className: "bg-blue-500/10 text-blue-400 animate-pulse" },
  ocr_complete:   { label: "OCR Done",      className: "bg-blue-500/10 text-blue-400" },
  extracting:     { label: "Extracting",    className: "bg-primary/10 text-primary" },
  extracted:      { label: "Extracted",     className: "bg-primary/10 text-primary" },
  categorized:    { label: "Categorized",   className: "bg-green-500/10 text-green-400" },
  reconciled:     { label: "Reconciled",    className: "bg-green-500/15 text-green-300" },
  error:          { label: "Error",         className: "bg-red-500/10 text-red-400" },
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const config = STATUS_CONFIG[status] ?? { label: status, className: "bg-muted text-muted-foreground" };
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium", config.className)}>
      {config.label}
    </span>
  );
}
