import { Sparkles } from "lucide-react";

import { Banner } from "@/components/ui/banner";

interface AiSummaryProps {
  text: string;
  loading?: boolean;
}

export function AiSummary({ text, loading }: AiSummaryProps) {
  if (loading) {
    return (
      <Banner variant="muted" icon={<Sparkles className="size-4 text-accent" />}>
        <div className="space-y-2">
          <div className="h-3 w-3/4 animate-pulse rounded bg-border" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-border" />
        </div>
      </Banner>
    );
  }

  return (
    <Banner variant="muted" icon={<Sparkles className="size-4 text-accent" />}>
      <p className="text-sm leading-relaxed text-neutral-200">{text}</p>
    </Banner>
  );
}
