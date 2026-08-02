// 21st.dev katalogundan uyarlandı (@serafimcloud/banner, shadcn formatı).
// isClosable/action/Button bağımlılığı kaldırıldı — bu projede banner hiç
// kapatılmıyor, tek kullanım yeri statik bir AI özet kutusu.
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const bannerVariants = cva("relative w-full", {
  variants: {
    variant: {
      default: "border border-border bg-surface",
      muted: "bg-surface-hover",
    },
    size: {
      sm: "px-4 py-2",
      default: "px-4 py-3",
    },
    rounded: {
      none: "",
      default: "rounded-lg",
    },
  },
  defaultVariants: {
    variant: "default",
    size: "default",
    rounded: "default",
  },
});

interface BannerProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof bannerVariants> {
  icon?: React.ReactNode;
}

const Banner = React.forwardRef<HTMLDivElement, BannerProps>(
  ({ className, variant, size, rounded, icon, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(bannerVariants({ variant, size, rounded }), className)}
      {...props}
    >
      <div className="flex items-start gap-3">
        {icon && <div className="flex shrink-0 items-center">{icon}</div>}
        <div className="grow">{children}</div>
      </div>
    </div>
  ),
);
Banner.displayName = "Banner";

export { Banner, type BannerProps };
