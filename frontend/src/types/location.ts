export interface ContactInfo {
  name: string;
  email: string;
  phone: string;
}

export interface LocationContacts {
  owner_1: ContactInfo;
  owner_2: ContactInfo;
  manager_1: ContactInfo;
  manager_2: ContactInfo;
}

export interface BusinessHours {
  [day: string]: { open: string; close: string; closed: boolean };
}

export interface Location {
  id: string;
  tenant_id: string;
  name: string;
  address: string | null;
  timezone: string;
  toast_location_id: string | null;
  store_id: string | null;
  is_active: boolean;
  uber_eats_id: string | null;
  skip_the_dishes_id: string | null;
  doordash_id: string | null;
  google_place_id: string | null;
  business_hours: BusinessHours | null;
  rent_monthly_incl_hst: string | null;
  contacts: LocationContacts | null;
  invite_email: string | null;
  invite_status: "none" | "pending" | "accepted";
  created_at: string;
  updated_at: string;
}
