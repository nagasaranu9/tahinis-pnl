"use client";

import { useCallback, useState } from "react";
import { useUploadDocument } from "@/hooks/use-documents";
import { cn } from "@/lib/utils";
import { Upload, AlertCircle, CheckCircle, Loader2 } from "lucide-react";

const ALLOWED_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/tiff"];
const MAX_SIZE_MB = 50;

interface FileStatus {
  id: string;
  name: string;
  status: "pending" | "uploading" | "done" | "error";
  message?: string;
}

export function UploadDropzone() {
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState<FileStatus[]>([]);
  const { mutateAsync: upload } = useUploadDocument();

  const isUploading = queue.some((f) => f.status === "pending" || f.status === "uploading");

  const handleFiles = useCallback(
    async (files: File[]) => {
      const entries: FileStatus[] = files.map((f, i) => ({
        id: `${Date.now()}-${i}-${f.name}`,
        name: f.name,
        status: "pending",
      }));
      setQueue((prev) => [...prev, ...entries]);

      // Upload sequentially — keeps OCR queue and progress UI predictable for
      // a batch of invoices dropped at once, rather than racing N parallel requests.
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const entryId = entries[i].id;

        if (!ALLOWED_TYPES.includes(file.type)) {
          setQueue((prev) =>
            prev.map((e) =>
              e.id === entryId
                ? { ...e, status: "error", message: "Unsupported type" }
                : e
            )
          );
          continue;
        }
        if (file.size > MAX_SIZE_MB * 1024 * 1024) {
          setQueue((prev) =>
            prev.map((e) =>
              e.id === entryId
                ? { ...e, status: "error", message: `Exceeds ${MAX_SIZE_MB}MB` }
                : e
            )
          );
          continue;
        }

        setQueue((prev) =>
          prev.map((e) => (e.id === entryId ? { ...e, status: "uploading" } : e))
        );
        try {
          await upload(file);
          setQueue((prev) =>
            prev.map((e) => (e.id === entryId ? { ...e, status: "done" } : e))
          );
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : "Upload failed";
          setQueue((prev) =>
            prev.map((e) => (e.id === entryId ? { ...e, status: "error", message: msg } : e))
          );
        }
      }
    },
    [upload]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length) handleFiles(files);
    },
    [handleFiles]
  );

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length) handleFiles(files);
    e.target.value = "";
  };

  const doneCount = queue.filter((f) => f.status === "done").length;
  const errorCount = queue.filter((f) => f.status === "error").length;

  return (
    <div className="space-y-3">
      <label
        className={cn(
          "flex flex-col items-center justify-center gap-3 border-2 border-dashed rounded-lg p-8 cursor-pointer transition-colors",
          dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50",
          isUploading && "pointer-events-none opacity-60"
        )}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          type="file"
          multiple
          className="hidden"
          accept=".pdf,.png,.jpg,.jpeg,.tiff"
          onChange={onInputChange}
          disabled={isUploading}
        />
        {isUploading ? (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-sm">
              Uploading {doneCount + errorCount + 1} of {queue.length}…
            </span>
          </div>
        ) : (
          <>
            <Upload className="h-8 w-8 text-muted-foreground" />
            <div className="text-center">
              <p className="text-sm font-medium">Drop invoices or receipts here</p>
              <p className="text-xs text-muted-foreground mt-1">
                PDF, PNG, JPG, TIFF · max 50MB each · multiple files supported
              </p>
            </div>
          </>
        )}
      </label>

      {queue.length > 0 && (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {queue.map((f) => (
            <div key={f.id} className="flex items-center gap-2 text-xs">
              {f.status === "uploading" && (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
              )}
              {f.status === "pending" && (
                <div className="h-3.5 w-3.5 shrink-0 rounded-full border border-border" />
              )}
              {f.status === "done" && (
                <CheckCircle className="h-3.5 w-3.5 shrink-0 text-green-400" />
              )}
              {f.status === "error" && (
                <AlertCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
              )}
              <span className="truncate flex-1">{f.name}</span>
              {f.status === "error" && (
                <span className="text-destructive shrink-0">{f.message}</span>
              )}
              {f.status === "done" && (
                <span className="text-muted-foreground shrink-0">processing</span>
              )}
            </div>
          ))}
          {!isUploading && (doneCount > 0 || errorCount > 0) && (
            <button
              onClick={() => setQueue([])}
              className="text-xs text-muted-foreground hover:text-foreground underline mt-1"
            >
              Clear ({doneCount} uploaded{errorCount > 0 ? `, ${errorCount} failed` : ""})
            </button>
          )}
        </div>
      )}
    </div>
  );
}
