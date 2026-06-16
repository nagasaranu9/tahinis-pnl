export const EXPENSE_CATEGORIES = [
  "Food Cost",
  "Beverage Cost",
  "Packaging",
  "Cleaning",
  "Utilities",
  "Rent",
  "Marketing",
  "Payroll",
  "Repairs",
  "Maintenance",
  "Insurance",
  "Software",
  "Professional Services",
  "Royalties",
  "Miscellaneous",
] as const;

export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number];

export interface Expense {
  id: string;
  tenant_id: string;
  location_id: string | null;
  document_id: string | null;
  vendor_name: string | null;
  amount: string | null;
  currency_code: string;
  expense_date: string;
  category: ExpenseCategory | null;
  ai_suggested_category: ExpenseCategory | null;
  ai_confidence_score: string | null;
  ai_explanation: string | null;
  is_ai_categorized: boolean;
  user_overridden: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExpenseListMeta {
  page: number;
  limit: number;
  total: number;
}

export interface ExpenseListResponse {
  data: Expense[];
  meta: ExpenseListMeta;
}
