import { BusinessCard } from "@/components/BusinessCard";
import type { ProviderResult } from "@/types";

const SKELETON_CARD_COUNT = 6;

interface ResultsGridProps {
  results: ProviderResult[];
  loading?: boolean;
}

export function ResultsGrid({ results, loading }: ResultsGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: SKELETON_CARD_COUNT }, (_, i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-xl border border-border bg-surface"
          />
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        Sonuç bulunamadı, farklı bir arama dene.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-4">
      {results.map((business) => (
        <BusinessCard key={business.id} business={business} />
      ))}
    </div>
  );
}
