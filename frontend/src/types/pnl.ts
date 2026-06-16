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
  net_profit: string | null;
  cogs_pct: string | null;
  labor_pct: string | null;
  prime_cost_pct: string | null;
  ebitda_pct: string | null;
  net_profit_pct: string | null;
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
