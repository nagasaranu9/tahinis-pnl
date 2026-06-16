import { apiClient } from "@/lib/api-client";

export async function downloadPnL(params: {
  format: "csv" | "pdf";
  period_start: string;
  period_end: string;
  location_id?: string;
}): Promise<void> {
  const qs = new URLSearchParams({
    format: params.format,
    period_start: params.period_start,
    period_end: params.period_end,
  });
  if (params.location_id) qs.set("location_id", params.location_id);

  const response = await apiClient.get(`/api/v1/pnl/export?${qs}`, {
    responseType: "blob",
  });

  const mimeType =
    params.format === "pdf" ? "application/pdf" : "text/csv";
  const blob = new Blob([response.data as BlobPart], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `tahinis_pnl_${params.period_start}_${params.period_end}.${params.format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
