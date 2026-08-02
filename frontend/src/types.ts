// backend/api/schemas.py ile senkron tutulur (kaynak orasıdır) — sadece
// /recommend akışında kullanılan alanlar burada, backend'deki tüm şema
// birebir aynalanmıyor.

export interface ProviderResult {
  id: number;
  title: string;
  type_normalized: string;
  rating: number | null;
  weighted_rating: number | null;
  price_min: number;
  price_max: number;
  address: string | null;
  phone: string | null;
  online_available: boolean;
  gender: string;
  services: string[];
  tags: string[];
  rich_description: string | null;
  distance_km: number | null;
}

export interface RecommendationResponse {
  recommendation: string;
  results: ProviderResult[];
  total: number;
}

export interface RecommendRequest {
  query: string;
  user_id: number;
  limit?: number;
  offset?: number;
}
