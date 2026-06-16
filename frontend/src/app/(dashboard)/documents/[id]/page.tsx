"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { format } from "date-fns";
import {
  ArrowLeft,
  RefreshCw,
  Trash2,
  ExternalLink,
  Pencil,
  Check,
  X,
  CheckCircle2,
} from "lucide-react";
import {
  useDocument,
  useDeleteDocument,
  useReprocessDocument,
  useCorrectLineItem,
} from "@/hooks/use-documents";
import { DocumentStatusBadge } from "@/components/documents/document-status-badge";
import { apiClient } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";
import type { OCRResult, LineItem } from "@/types/document";

function formatCurrency(amount: string | null | undefined, currency: string): string {
  if (!amount) return "—";
  const n = parseFloat(amount);
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(n);
}

// ─── Editable Line Item Row ───────────────────────────────────────────────────

function LineItemRow({
  item,
  documentId,
}: {
  item: LineItem;
  documentId: string;
}) {
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState({
    description: item.description,
    quantity: item.quantity ?? "",
    unit_price: item.unit_price ?? "",
    amount: item.amount,
  });
  const { mutate: correct, isPending: saving } = useCorrectLineItem(documentId);

  function handleSave() {
    correct(
      {
        lineItemId: item.id,
        description: fields.description || undefined,
        quantity: fields.quantity || null,
        unit_price: fields.unit_price || null,
        amount: fields.amount || undefined,
      },
      {
        onSuccess: () => setEditing(false),
      }
    );
  }

  function handleCancel() {
    setFields({
      description: item.description,
      quantity: item.quantity ?? "",
      unit_price: item.unit_price ?? "",
      amount: item.amount,
    });
    setEditing(false);
  }

  const confidencePct = parseFloat(item.confidence_score) * 100;
  const confidenceColor =
    confidencePct >= 80
      ? "text-green-400"
      : confidencePct >= 50
      ? "text-yellow-400"
      : "text-red-400";

  if (editing) {
    return (
      <tr className="bg-primary/5 border-b border-border">
        <td className="px-3 py-2">
          <input
            value={fields.description}
            onChange={(e) => setFields((f) => ({ ...f, description: e.target.value }))}
            className="w-full text-sm bg-background border border-input rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
            autoFocus
          />
        </td>
        <td className="px-3 py-2">
          <input
            value={fields.quantity}
            onChange={(e) => setFields((f) => ({ ...f, quantity: e.target.value }))}
            className="w-20 text-sm text-right bg-background border border-input rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </td>
        <td className="px-3 py-2">
          <input
            value={fields.unit_price}
            onChange={(e) => setFields((f) => ({ ...f, unit_price: e.target.value }))}
            className="w-24 text-sm text-right bg-background border border-input rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </td>
        <td className="px-3 py-2">
          <input
            value={fields.amount}
            onChange={(e) => setFields((f) => ({ ...f, amount: e.target.value }))}
            className="w-24 text-sm text-right bg-background border border-input rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </td>
        <td className="px-3 py-2 text-right text-xs text-muted-foreground">
          {confidencePct.toFixed(0)}%
        </td>
        <td className="px-3 py-2">
          <div className="flex gap-1">
            <button
              onClick={handleSave}
              disabled={saving}
              className="p-1 rounded bg-green-500/10 text-green-400 hover:bg-green-500/20 disabled:opacity-50"
              title="Save"
            >
              {saving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            </button>
            <button
              onClick={handleCancel}
              className="p-1 rounded bg-muted text-muted-foreground hover:bg-muted/60"
              title="Cancel"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr
      className={`border-b border-border group ${
        item.manually_corrected ? "bg-blue-500/5" : "hover:bg-muted/20"
      } transition-colors`}
    >
      <td className="px-3 py-2 text-sm">
        <span className="flex items-center gap-1.5">
          {item.description}
          {item.manually_corrected && (
            <CheckCircle2 className="h-3 w-3 text-blue-400 shrink-0" aria-label="Manually corrected" />
          )}
        </span>
      </td>
      <td className="px-3 py-2 text-right text-sm text-muted-foreground">
        {item.quantity ?? "—"}
      </td>
      <td className="px-3 py-2 text-right text-sm text-muted-foreground">
        {item.unit_price ? formatCurrency(item.unit_price, item.currency_code) : "—"}
      </td>
      <td className="px-3 py-2 text-right text-sm font-medium">
        {formatCurrency(item.amount, item.currency_code)}
      </td>
      <td className={`px-3 py-2 text-right text-xs font-mono ${confidenceColor}`}>
        {confidencePct.toFixed(0)}%
      </td>
      <td className="px-3 py-2">
        <button
          onClick={() => setEditing(true)}
          className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
          title="Edit line item"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </td>
    </tr>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: doc, isLoading } = useDocument(id);
  const { mutate: deleteDoc, isPending: deleting } = useDeleteDocument();
  const { mutate: reprocess, isPending: reprocessing } = useReprocessDocument();

  const { data: ocrData } = useQuery({
    queryKey: ["document-ocr", id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: OCRResult }>(`/api/v1/documents/${id}/ocr`);
      return data.data;
    },
    enabled:
      !!id &&
      !!doc &&
      ["ocr_complete", "extracted", "categorized", "reconciled"].includes(doc.status),
    retry: false,
  });

  const { data: lineItemsData } = useQuery({
    queryKey: ["document-line-items", id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ data: LineItem[] }>(
        `/api/v1/documents/${id}/line-items`
      );
      return data.data;
    },
    enabled: !!id && !!doc && doc.status !== "pending" && doc.status !== "ocr_processing",
    retry: false,
  });

  if (isLoading) {
    return <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>;
  }
  if (!doc) {
    return (
      <div className="py-12 text-center text-sm text-destructive">Document not found.</div>
    );
  }

  function handleDelete() {
    if (!confirm("Delete this document? This cannot be undone.")) return;
    deleteDoc(id, { onSuccess: () => router.push("/documents") });
  }

  const correctedCount = lineItemsData?.filter((li) => li.manually_corrected).length ?? 0;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold truncate max-w-lg">{doc.original_filename}</h1>
            <div className="flex items-center gap-2 mt-1">
              <DocumentStatusBadge status={doc.status} />
              {doc.is_duplicate && (
                <span className="text-xs text-orange-400 font-medium">Duplicate</span>
              )}
              {correctedCount > 0 && (
                <span className="text-xs text-blue-400 font-medium">
                  {correctedCount} line item{correctedCount !== 1 ? "s" : ""} corrected
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {doc.download_url && (
            <a
              href={doc.download_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 px-3 py-1.5 text-sm border border-border rounded-md hover:bg-muted/50 transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Download
            </a>
          )}
          <button
            onClick={() => reprocess(id)}
            disabled={reprocessing}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border border-border rounded-md hover:bg-muted/50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${reprocessing ? "animate-spin" : ""}`} />
            Reprocess
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border border-destructive text-destructive rounded hover:bg-destructive/10 disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      </div>

      {/* Metadata */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Vendor", value: doc.vendor_name ?? "—" },
          { label: "Amount", value: formatCurrency(doc.total_amount, doc.currency_code) },
          {
            label: "Date",
            value: doc.document_date
              ? format(new Date(doc.document_date), "MMM d, yyyy")
              : "—",
          },
          { label: "Type", value: doc.document_type },
          { label: "Source", value: doc.source.replace("_", " ") },
          { label: "Size", value: `${(doc.file_size_bytes / 1024).toFixed(1)} KB` },
          { label: "Uploaded", value: format(new Date(doc.created_at), "MMM d, yyyy") },
          { label: "MIME", value: doc.mime_type },
        ].map(({ label, value }) => (
          <div key={label} className="space-y-1">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              {label}
            </p>
            <p className="text-sm">{value}</p>
          </div>
        ))}
      </div>

      {/* Line Items — with inline edit */}
      {lineItemsData && lineItemsData.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Line Items</h2>
            <p className="text-xs text-muted-foreground">
              Hover row → click pencil to correct OCR errors
            </p>
          </div>
          <div className="rounded-lg border border-border overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 border-b border-border">
                <tr>
                  <th className="text-left px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Description
                  </th>
                  <th className="text-right px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Qty
                  </th>
                  <th className="text-right px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Unit Price
                  </th>
                  <th className="text-right px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Amount
                  </th>
                  <th className="text-right px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Conf.
                  </th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {lineItemsData.map((item) => (
                  <LineItemRow key={item.id} item={item} documentId={id} />
                ))}
              </tbody>
            </table>
          </div>
          {correctedCount > 0 && (
            <p className="text-xs text-blue-400 flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {correctedCount} line item{correctedCount !== 1 ? "s" : ""} manually corrected.
              Source document is unchanged — only extracted values were updated.
            </p>
          )}
        </div>
      )}

      {/* OCR Text */}
      {ocrData && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Extracted Text</h2>
            <span className="text-xs text-muted-foreground">
              {ocrData.provider} ·{" "}
              {(parseFloat(ocrData.confidence_score) * 100).toFixed(1)}% confidence ·{" "}
              {ocrData.page_count} page{ocrData.page_count !== 1 ? "s" : ""}
            </span>
          </div>
          <pre className="bg-muted/20 rounded-lg p-4 text-xs overflow-auto max-h-64 whitespace-pre-wrap font-mono border border-border text-muted-foreground">
            {ocrData.extracted_text}
          </pre>
        </div>
      )}

      {/* Inline document preview */}
      {doc.download_url && (
        <div className="space-y-3">
          <h2 className="text-base font-semibold">Document Preview</h2>
          {doc.mime_type === "application/pdf" ? (
            <div className="rounded-lg border border-border overflow-hidden bg-card" style={{ height: "600px" }}>
              <iframe
                src={doc.download_url}
                className="w-full h-full"
                title={doc.original_filename}
              />
            </div>
          ) : doc.mime_type?.startsWith("image/") ? (
            <div className="rounded-lg border border-border overflow-hidden bg-card p-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={doc.download_url}
                alt={doc.original_filename}
                className="max-w-full max-h-[600px] object-contain mx-auto block"
              />
            </div>
          ) : null}
        </div>
      )}

      {doc.status === "error" && (
        <div className="rounded-md bg-destructive/10 border border-destructive/30 p-4 text-sm text-destructive">
          Processing error. Click Reprocess to retry.
        </div>
      )}
    </div>
  );
}
