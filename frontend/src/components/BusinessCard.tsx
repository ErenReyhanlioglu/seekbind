import { MapPin, Star } from "lucide-react";

import type { ProviderResult } from "@/types";

const MAX_VISIBLE_TAGS = 3;

interface BusinessCardProps {
  business: ProviderResult;
}

export function BusinessCard({ business }: BusinessCardProps) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 transition-colors hover:border-accent/40 hover:bg-surface-hover">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium text-neutral-100">{business.title}</h3>
          <p className="text-xs text-neutral-500">{business.type_normalized}</p>
        </div>
        {business.weighted_rating !== null && (
          <div className="flex shrink-0 items-center gap-1 text-xs text-accent">
            <Star className="size-3.5 fill-accent" />
            {business.weighted_rating.toFixed(1)}
          </div>
        )}
      </div>

      {business.address && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-neutral-400">
          <MapPin className="size-3.5 shrink-0 text-neutral-500" />
          {business.address}
        </p>
      )}

      <p className="mt-1.5 text-xs text-neutral-400">
        {business.price_min}–{business.price_max} ₺
      </p>

      {business.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {business.tags.slice(0, MAX_VISIBLE_TAGS).map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-accent/10 px-2 py-0.5 text-xs text-accent"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
