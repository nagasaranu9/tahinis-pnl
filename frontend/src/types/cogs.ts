export interface CogsCategoryRow {
  category: string;
  opening_inventory: string;
  purchases: string;
  ending_inventory: string;
  cogs: string;
}

export interface CogsTotals {
  opening_inventory: string;
  purchases: string;
  ending_inventory: string;
  cogs: string;
  cogs_pct: string | null;
}

export interface CogsReport {
  week_ending: string;
  has_prior_week: boolean;
  net_sales: string;
  net_sales_is_override: boolean;
  purchases_is_override: boolean;
  categories: CogsCategoryRow[];
  totals: CogsTotals;
}

export interface CogsItem {
  category: string;
  item_name: string;
  pack_size: string | null;
  unit: string | null;
  cases: string | null;
  packs: string | null;
  weight: string | null;
  unit_price: string | null;
  extended_total: string;
}

export interface CogsWeekSummary {
  id: string;
  week_ending: string;
  location_id: string | null;
  original_filename: string | null;
  created_at: string | null;
  net_sales: string;
  totals: CogsTotals;
}

export interface CogsWeekDetail {
  id: string;
  week_ending: string;
  location_id: string | null;
  original_filename: string | null;
  created_at: string | null;
  report: CogsReport;
  items: CogsItem[];
}
