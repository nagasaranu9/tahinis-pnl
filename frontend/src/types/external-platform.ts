export interface GoogleReviewSnapshot {
  id: string;
  tenant_id: string;
  location_id: string | null;
  snapshot_date: string;
  rating_average: string | null;
  review_count_total: number;
  new_reviews_count: number;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  google_place_id: string | null;
  created_at: string;
}

export interface GoogleAdsCampaign {
  id: string;
  tenant_id: string;
  location_id: string | null;
  google_campaign_id: string;
  google_customer_id: string;
  name: string;
  status: string;
  campaign_type: string | null;
}

export interface GoogleAdsDailyMetric {
  id: string;
  campaign_id: string;
  metric_date: string;
  spend: string | null;
  impressions: number;
  clicks: number;
  conversions: string | null;
  roas: string | null;
  currency_code: string;
}

export interface GoogleAdsSummary {
  period_start: string;
  period_end: string;
  total_spend: string;
  total_impressions: number;
  total_clicks: number;
  total_conversions: string;
  average_roas: string | null;
  campaigns: GoogleAdsCampaign[];
  daily_metrics: GoogleAdsDailyMetric[];
}
