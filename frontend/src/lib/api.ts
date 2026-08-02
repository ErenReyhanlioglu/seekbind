import type { RecommendationResponse } from "../types";

// vite dev server varsayılan olarak backend'i localhost:8000'de bekler
// (uv run uvicorn backend.main:app --reload) — farklı bir portta
// çalıştırıyorsan frontend/.env içinde VITE_API_BASE_URL'i güncelle.
const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// backend/api/schemas.py:RecommendRequest.user_id zorunlu ama bu demo'da
// giriş akışı yok — DB'deki tek referans test kullanıcısı (id=1,
// scripts/seed_test_user.py) kullanılıyor, reseed sonrası ID değişirse
// frontend/.env'den güncellenir.
const DEMO_USER_ID: number = Number(import.meta.env.VITE_DEMO_USER_ID ?? 1);

export class ApiError extends Error {}

export async function recommend(
  query: string,
  signal: AbortSignal,
): Promise<RecommendationResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, user_id: DEMO_USER_ID }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw e; // çağıran (App.tsx) bunu görmezden gelir, hata değil
    }
    throw new ApiError("Sunucuya ulaşılamadı, backend'in çalıştığından emin ol");
  }

  if (!response.ok) {
    throw new ApiError("Arama başarısız oldu, lütfen tekrar dene");
  }

  return (await response.json()) as RecommendationResponse;
}
