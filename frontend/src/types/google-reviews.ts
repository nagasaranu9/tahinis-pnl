export interface GoogleReviewConfig {
  id: string;
  location_id: string;
  place_id: string;
  account_name: string | null;
  location_name: string | null;
  is_active: boolean;
  last_synced_at: string | null;
}

export interface GoogleReview {
  id: string;
  review_id: string;
  author_name: string | null;
  rating: number | null;
  comment: string | null;
  published_at: string | null;
  reply_comment: string | null;
}

export interface ReviewsSummary {
  average_rating: number | null;
  total_review_count: number;
  five_star: number;
  four_star: number;
  three_star: number;
  two_star: number;
  one_star: number;
  recent_reviews: GoogleReview[];
}
