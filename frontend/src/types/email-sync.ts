export interface EmailSyncConfig {
  id: string;
  provider: "gmail" | "outlook";
  email_address: string | null;
  is_active: boolean;
  last_synced_at: string | null;
}

export interface EmailSyncJob {
  id: string;
  config_id: string;
  provider: string;
  status: "pending" | "running" | "complete" | "failed";
  started_at: string | null;
  completed_at: string | null;
  messages_scanned: number;
  attachments_found: number;
  documents_created: number;
  duplicates_skipped: number;
  error_message: string | null;
  created_at: string;
}

export interface DriveSyncConfig {
  id: string;
  email_address: string | null;
  is_active: boolean;
  last_synced_at: string | null;
}
