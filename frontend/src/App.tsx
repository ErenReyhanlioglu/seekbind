import { useEffect, useRef, useState } from "react";

import { AiSummary } from "@/components/AiSummary";
import { ResultsGrid } from "@/components/ResultsGrid";
import { SearchBar } from "@/components/SearchBar";
import { ApiError, recommend } from "@/lib/api";
import type { RecommendationResponse } from "@/types";

type Status = "idle" | "loading" | "success" | "error";

function App() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!query.trim()) return;

    abortRef.current?.abort(); // önceki isteği iptal et (art arda arama)
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("loading");
    setErrorMessage("");

    try {
      const response = await recommend(query, controller.signal);
      setData(response);
      setStatus("success");
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setErrorMessage(
        e instanceof ApiError ? e.message : "Beklenmeyen bir hata oluştu",
      );
      setStatus("error");
    }
  }

  const hasSearched = status !== "idle";

  return (
    <div className="mx-auto min-h-svh max-w-5xl px-6 py-10">
      <SearchBar
        variant={hasSearched ? "compact" : "hero"}
        value={query}
        onChange={setQuery}
        onSubmit={handleSubmit}
        loading={status === "loading"}
      />

      {status === "error" && (
        <p className="mt-4 text-sm text-red-400">{errorMessage}</p>
      )}

      {(status === "loading" || status === "success") && (
        <div className="mt-8 space-y-6">
          <AiSummary text={data?.recommendation ?? ""} loading={status === "loading"} />
          <ResultsGrid results={data?.results ?? []} loading={status === "loading"} />
        </div>
      )}
    </div>
  );
}

export default App;
