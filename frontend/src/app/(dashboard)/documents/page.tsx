"use client";

import { useState } from "react";
import { useDocuments } from "@/hooks/use-documents";
import { UploadDropzone } from "@/components/documents/upload-dropzone";
import { DocumentTable } from "@/components/documents/document-table";

export default function DocumentsPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useDocuments({ page, limit: 50 });

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
            {data?.meta.total ?? 0} documents
          </h2>
        </div>

        {isLoading && (
          <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>
        )}
        {isError && (
          <div className="py-12 text-center text-sm text-destructive">Failed to load documents.</div>
        )}
        {data && <DocumentTable documents={data.data} />}

        {data && data.meta.total > data.meta.limit && (
          <div className="flex justify-center gap-2 pt-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 text-sm border border-border rounded-md disabled:opacity-40 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              Previous
            </button>
            <span className="px-3 py-1 text-sm text-muted-foreground">
              Page {page}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page * data.meta.limit >= data.meta.total}
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
