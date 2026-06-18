export interface ToastSyncConfig {
  location_id: string;
  toast_restaurant_guid: string;
  is_active: boolean;
  historical_import_complete: boolean;
  last_synced_at: string | null;
  historical_status: "pending" | "running" | "complete" | "failed" | null;
  historical_started_at: string | null;
  historical_orders_synced: number | null;
  historical_error: string | null;
}

export type SyncJobStatus = "pending" | "running" | "complete" | "failed";
export type SyncJobType = "incremental" | "historical" | "manual";

export interface ToastSyncJob {
  id: string;
  location_id: string;
  job_type: SyncJobType;
  status: SyncJobStatus;
  started_at: string | null;
  completed_at: string | null;
  date_from: string | null;
  date_to: string | null;
  orders_synced: number;
  employees_synced: number;
  time_entries_synced: number;
  error_message: string | null;
  triggered_by: string | null;
  created_at: string;
}
