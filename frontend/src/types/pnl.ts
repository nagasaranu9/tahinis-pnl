export interface PnLLineItems {
  gross_revenue: string | null;
  total_discounts: string | null;
  net_revenue: string | null;
  cogs: string | null;
  gross_profit: string | null;
  labor_cost: string | null;
  prime_cost: string | null;
  operating_expenses: string | null;
  ebitda: string | null;
  interest_expense: string | null;
  net_profit: string | null;
  cogs_pct: string | null;
  labor_pct: string | null;
  prime_cost_pct: string | null;
  ebitda_pct: string | null;
  net_profit_pct: string | null;
}

export type BenchmarkStatus = "good" | "watch" | "bad" | "unknown";

export interface BenchmarkChip {
  metric: string;
  label: string;
  value_pct: string | null;
  target_label: string;
  status: BenchmarkStatus;
}

export interface DiscountBreakdownRow {
  name: string;
  scope: string;
  total: string;
  count: number;
  pct_of_discounts: string | null;
}

export interface DiscountBreakdown {
  total: string;
  currency_code: string;
  discounts: DiscountBreakdownRow[];
}

export interface PnLTrendPoint {
  period_label: string;
  period_start: string;
  net_revenue: string | null;
  cogs: string | null;
  cogs_pct: string | null;
  labor_cost: string | null;
  labor_pct: string | null;
  prime_cost_pct: string | null;
  ebitda: string | null;
  net_profit: string | null;
  net_profit_pct: string | null;
}

export interface PnLTrend {
  months: number;
  points: PnLTrendPoint[];
}

export interface ExpenseLineItem {
  vendor_name: string | null;
  amount: string;
}

export interface ExpenseCategoryBreakdown {
  category: string;
  total: string;
  expense_count: number;
  expenses: ExpenseLineItem[];
}

export interface PnLReport {
  tenant_id: string;
  location_id: string | null;
  period_start: string;
  period_end: string;
  currency_code: string;
  line_items: PnLLineItems;
  expense_breakdown: ExpenseCategoryBreakdown[];
  benchmarks: BenchmarkChip[];
  order_count: number;
  expense_count: number;
  bank_statement_verified: boolean;
  bank_statement_warning: string | null;
}

export interface PnLSnapshot {
  id: string;
  tenant_id: string;
  location_id: string | null;
  period_start: string;
  period_end: string;
  period_label: string;
  gross_revenue: string | null;
  net_revenue: string | null;
  cogs: string | null;
  gross_profit: string | null;
  labor_cost: string | null;
  ebitda: string | null;
  net_profit: string | null;
  order_count: number;
  expense_count: number;
}

// ─── Bank-statement-basis P&L ────────────────────────────────────────────────

export interface BankBasisSide {
  revenue: string;
  ebitda: string;
  net_profit: string;
}

export interface BankPartnerSplit {
  name: string;
  share_pct: string;
  revenue_before_hst: string;
  revenue_after_hst: string;
  net_before_hst: string;
  net_after_hst: string;
}

export interface BankBasisPnL {
  period_start: string;
  period_end: string;
  basis: string;
  revenue: string;
  revenue_by_channel: Record<string, string>;
  cogs: string;
  labor: string;
  operating_expenses: string;
  interest: string;
  expense_by_category: Record<string, string>;
  principal_excluded: string;
  before_hst: BankBasisSide;
  after_hst: BankBasisSide;
  hst: {
    collected_on_sales: string;
    input_tax_credits: string;
    net_remittance: string;
  };
  partner_split: BankPartnerSplit[];
}

export interface Partner {
  name: string;
  share_pct: string;
}
