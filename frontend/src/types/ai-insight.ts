export type InsightType =
  | "expense_anomaly"
  | "revenue_trend"
  | "pnl_summary"
  | "category_analysis"
  | "reconciliation_summary"
  | "labor_efficiency"
  | "vendor_analysis";

export type InsightSeverity = "info" | "warning" | "critical";

export const INSIGHT_TYPES: InsightType[] = [
  "pnl_summary",
  "category_analysis",
  "expense_anomaly",
  "revenue_trend",
  "reconciliation_summary",
  "labor_efficiency",
  "vendor_analysis",
];

export const INSIGHT_TYPE_LABELS: Record<InsightType, string> = {
  pnl_summary: "P&L Summary",
  category_analysis: "Category Analysis",
  expense_anomaly: "Expense Anomaly",
  revenue_trend: "Revenue Trend",
  reconciliation_summary: "Reconciliation Summary",
  labor_efficiency: "Labor Efficiency",
  vendor_analysis: "Vendor Analysis",
};

export interface AIInsight {
  id: string;
  tenant_id: string;
  location_id: string | null;
  insight_type: InsightType;
  severity: InsightSeverity;
  title: string;
  summary: string;
  explanation: string;
  confidence_score: string;
  period_start: string | null;
  period_end: string | null;
  document_id: string | null;
  expense_id: string | null;
  reconciliation_run_id: string | null;
  is_dismissed: boolean;
  is_helpful: boolean | null;
  model_id: string | null;
  created_at: string;
}
