"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type LoadMoreButtonProps = {
  onClick: () => void;
  isLoading?: boolean;
  disabled?: boolean;
  remaining?: number;
  className?: string;
};

export function LoadMoreButton({
  onClick,
  isLoading = false,
  disabled = false,
  remaining,
  className,
}: LoadMoreButtonProps) {
  const isDisabled = disabled || isLoading;

  return (
    <div className={cn("flex justify-center py-6", className)}>
      <button
        type="button"
        onClick={onClick}
        disabled={isDisabled}
        className="btn-press btn-glow flex items-center gap-2 px-6 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:translate-y-[-1px]"
        style={{
          backgroundColor: "rgba(255, 255, 255, 0.05)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          color: "rgba(255, 255, 255, 0.75)",
        }}
      >
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading...
          </>
        ) : (
          <>
            Load More
            {typeof remaining === "number" && remaining > 0 && (
              <span
                className="px-2 py-0.5 rounded-md text-[11px] font-semibold"
                style={{
                  backgroundColor: "rgba(138, 92, 255, 0.12)",
                  color: "#C7BFFF",
                }}
              >
                {remaining}
              </span>
            )}
          </>
        )}
      </button>
    </div>
  );
}
