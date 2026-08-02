import { Search } from "lucide-react";

import { cn } from "@/lib/utils";

interface SearchBarProps {
  variant: "hero" | "compact";
  value: string;
  onChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  loading?: boolean;
}

export function SearchBar({ variant, value, onChange, onSubmit, loading }: SearchBarProps) {
  const isHero = variant === "hero";

  return (
    <div className={cn(isHero && "flex flex-col items-center gap-4 pt-20 pb-4")}>
      {isHero && (
        <h1 className="text-2xl font-medium text-neutral-100">Ne arıyorsun?</h1>
      )}
      <form
        onSubmit={onSubmit}
        className={cn("flex gap-2", isHero ? "w-full max-w-xl" : "w-full")}
      >
        <div className="relative flex-1">
          <Search className="absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-neutral-500" />
          <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="ör. miras davası için deneyimli bir avukat"
            className={cn(
              "w-full rounded-lg border border-border bg-surface pr-3 pl-10 text-sm text-neutral-100",
              "outline-none transition-colors placeholder:text-neutral-600 focus:border-accent",
              isHero ? "py-3" : "py-2.5",
            )}
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className={cn(
            "shrink-0 rounded-lg bg-accent px-4 font-medium text-accent-fg",
            "transition-opacity hover:opacity-90 disabled:opacity-50",
            isHero ? "py-3 text-sm" : "py-2.5 text-sm",
          )}
        >
          {loading ? "Aranıyor..." : "Ara"}
        </button>
      </form>
    </div>
  );
}
