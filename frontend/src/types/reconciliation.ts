export type ReconciliationStatus = "pending" | "running" | "complete" | "failed";
export type FlagSeverity = "low" | "medium" | "high" | "critical";
export type FlagType =
  | "missing_invoice"
  | "duplicate_invoice"
  | "duplicate_expense"
  | "uncategorized_expense"
  | "suspicious_amount"
  | "unmatched_sale"
  | "unverified_payroll";

export interface ReconciliationRun {
  id: string;
  tenant_id: string;
  location_id: string | null;
  period_start: string;
  period_end: string;
  status: ReconciliationStatus;
  triggered_by: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  documents_checked: number;
  expenses_checked: number;
  toast_orders_checked: number;
  flags_raised: number;
  total_sales_amount: string | null;
  total_expense_amount: string | null;
  net_variance: string | null;
  created_at: string;
}

export interface ReconciliationFlag {
  id: string;
  run_id: string;
  flag_type: FlagType;
  severity: FlagSeverity;
  message: string;
  document_id: string | null;
  expense_id: string | null;
  toast_order_id: string | null;
  is_resolved: boolean;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string;
}

export interface RunListMeta {
  page: number;
  limit: number;
  total: number;
}
