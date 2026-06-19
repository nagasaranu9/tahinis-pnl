"use client";

import { useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { useDocuments, useReprocessDocument, useDeleteAllDocuments } from "@/hooks/use-documents";
import { UploadDropzone } from "@/components/documents/upload-dropzone";
import { DocumentTable } from "@/components/documents/document-table";

export default function DocumentsPage() {
  const [page, setPage] = useState(1);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { data, isLoading, isError } = useDocuments({ page, limit: 50 });
  const { mutate: reprocess, isPending: reprocessing } = useReprocessDocument();
  const { mutate: deleteAll, isPending: deleting } = useDeleteAllDocuments();

  const pendingIds = (data?.data ?? [])
    .filter((d) => d.status === "pending" || d.status === "error")
    .map((d) => d.id);

  function reprocessAll() {
    for (const id of pendingIds) reprocess(id);
  }

  function handleDeleteAll() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    deleteAll(undefined, {
      onSuccess: () => {
        setConfirmDelete(false);
        setPage(1);
      },
      onError: () => setConfirmDelete(false),
    });
  }

  const total = data?.meta.total ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Documents</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload invoices, receipts, and bills for automatic processing.
        </p>
      </div>

      <UploadDropzone />

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">
            {total} documents
          </h2>
          <div className="flex items-center gap-2">
            {pendingIds.length > 0 && (
              <button
                onClick={reprocessAll}
                disabled={reprocessing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 disabled:opacity-50 transition-colors"
              >
                <RefreshCw className={`h-3 w-3 ${reprocessing ? "animate-spin" : ""}`} />
                Reprocess {pendingIds.length} pending
              </button>
            )}
            {total > 0 && (
              <button
                onClick={handleDeleteAll}
                disabled={deleting}
                onBlur={() => setConfirmDelete(false)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-md disabled:opacity-50 transition-colors ${
                  confirmDelete
                    ? "border-destructive text-destructive bg-destructive/10 hover:bg-destructive/20"
                    : "border-border text-muted-foreground hover:text-destructive hover:border-destructive hover:bg-destructive/5"
                }`}
              >
                <Trash2 className="h-3 w-3" />
                {confirmDelete ? "Confirm — delete all?" : `Delete all ${total}`}
              </button>
            )}
          </div>
        </div>

        {isLoading && (
          <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>
        )}
        {isError && (
          <div className="py-12 text-center text-sm text-destructive">Failed to load documents.</div>
        )}
        {data && <DocumentTable documents={data.data} />}

        {data && total > data.meta.limit && (
          <div className="flex justify-center gap-2 pt-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 text-sm border border-border rounded-md disabled:opacity-40 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              Previous
            </button>
            <span className="px-3 py-1 text-sm text-muted-foreground">
              Page {page} of {Math.ceil(total / data.meta.limit)}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page * data.meta.limit >= total}
              className="px-3 py-1 text-sm border border-border rounded-md disabled:opacity-40 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
