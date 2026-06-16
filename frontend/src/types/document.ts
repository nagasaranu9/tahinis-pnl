export type DocumentStatus =
  | "pending"
  | "ocr_processing"
  | "ocr_complete"
  | "extracting"
  | "extracted"
  | "categorized"
  | "reconciled"
  | "error";

export type DocumentType = "invoice" | "receipt" | "bill" | "statement" | "other";

export interface Document {
  id: string;
  tenant_id: string;
  location_id: string | null;
  source: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  status: DocumentStatus;
  document_type: DocumentType;
  document_date: string | null;
  vendor_name: string | null;
  total_amount: string | null;
  currency_code: string;
  is_duplicate: boolean;
  duplicate_of: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  download_url?: string | null;
}

export interface LineItem {
  id: string;
  description: string;
  quantity: string | null;
  unit_price: string | null;
  amount: string;
  currency_code: string;
  confidence_score: string;
  manually_corrected: boolean;
}

export interface OCRResult {
  id: string;
  provider: string;
  extracted_text: string;
  confidence_score: string;
  page_count: number;
  processing_time_ms: number | null;
  processed_at: string;
}
