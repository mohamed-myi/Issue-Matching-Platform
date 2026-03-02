"use client";

import Link from "next/link";
import { Bookmark, ExternalLink, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Route } from "next";

export type WhyThisItem = {
  entity: string;
  score: number;
};

export type IssueListItemModel = {
  nodeId: string;
  title: string;
  repoName: string;
  primaryLanguage: string | null;
  labels: string[];
  qScore: number | null;
  createdAt: string | null;
  bodyPreview?: string | null;
  whyThis?: WhyThisItem[] | null;
  githubUrl?: string | null;
};

type IssueListItemProps = {
  issue: IssueListItemModel;
  href: Route;
  isSaved?: boolean;
  onToggleSaved?: () => void;
};

export function IssueListItem({ issue, href, isSaved, onToggleSaved }: IssueListItemProps) {
  const score = issue.qScore;

  return (
    <div
      className="group relative hover:bg-white/[0.03] transition-colors"
      style={{
        borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
        background: "linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.0))",
        height: "72px",
        transition: "transform 150ms ease, background-color 150ms ease",
      }}
    >
      <div className="flex h-full items-center gap-6 pl-6 pr-5">
        <div className="min-w-0 flex-1">
          <span
            className="block truncate text-[14px] font-semibold leading-snug group-hover:underline decoration-1 underline-offset-2 cursor-pointer"
            style={{ color: "#E6E9F2", letterSpacing: "-0.01em" }}
          >
            {issue.title}
          </span>
          <div className="mt-1 flex items-center gap-2.5">
            <span className="text-[12px] font-medium" style={{ color: "#8A90B2" }}>
              {issue.repoName}
            </span>
            <div className="h-0.5 w-0.5 rounded-full" style={{ backgroundColor: "#8A90B2" }} />
            <span className="text-[12px] font-medium" style={{ color: "#8A90B2" }}>
              {issue.primaryLanguage ?? "Unknown"}
            </span>
            {issue.labels.length ? (
              <>
                <div className="h-0.5 w-0.5 rounded-full" style={{ backgroundColor: "#8A90B2" }} />
                <div className="flex items-center gap-1.5 truncate">
                  {issue.labels.slice(0, 3).map((label, idx) => (
                    <span key={label} className="text-[11px] font-semibold" style={{ color: "#A8AEFF" }}>
                      {label}
                      {idx < Math.min(3, issue.labels.length) - 1 ? ", " : ""}
                    </span>
                  ))}
                  {issue.labels.length > 3 ? (
                    <span className="text-[11px] font-semibold" style={{ color: "#A8AEFF" }}>
                      +{issue.labels.length - 3}
                    </span>
                  ) : null}
                </div>
              </>
            ) : null}
            {issue.whyThis && issue.whyThis.length > 0 && (
              <>
                <div className="h-0.5 w-0.5 rounded-full" style={{ backgroundColor: "#8A90B2" }} />
                <div
                  className="flex items-center gap-1 cursor-help"
                  title={`Why this matches your profile: ${issue.whyThis.map((w) => w.entity).join(", ")}`}
                >
                  <Sparkles className="h-3 w-3" style={{ color: "#10B981" }} />
                  <span className="text-[11px] font-medium" style={{ color: "#10B981" }}>
                    {issue.whyThis
                      .slice(0, 3)
                      .map((w) => w.entity)
                      .join(", ")}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-3">
          {typeof score === "number" ? (
            <div
              className="relative flex items-center justify-center"
              style={{ width: 36, height: 36 }}
              title="Quality score"
            >
              <svg
                className="absolute inset-0"
                width="36"
                height="36"
                viewBox="0 0 36 36"
              >
                <circle
                  cx="18"
                  cy="18"
                  r="15"
                  fill="none"
                  stroke="rgba(138, 92, 255, 0.15)"
                  strokeWidth="3"
                />
                <circle
                  cx="18"
                  cy="18"
                  r="15"
                  fill="none"
                  stroke="rgba(138, 92, 255, 0.8)"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeDasharray={`${score * 94.2} 94.2`}
                  transform="rotate(-90 18 18)"
                />
              </svg>
              <span
                className="text-[10px] font-semibold"
                style={{ color: "#C7BFFF" }}
              >
                {Math.round(score * 100)}
              </span>
            </div>
          ) : null}

          <button
            type="button"
            className={cn("btn-press rounded-xl p-2 transition-colors hover:bg-white/5", onToggleSaved ? "" : "opacity-50")}
            title={isSaved ? "Unsave" : "Save"}
            onClick={(e) => {
              e.stopPropagation();
              onToggleSaved?.();
            }}
            disabled={!onToggleSaved}
          >
            <Bookmark
              className="h-4 w-4"
              style={{ color: isSaved ? "rgba(138, 92, 255, 0.95)" : "rgba(255, 255, 255, 0.5)" }}
            />
          </button>

          {issue.githubUrl ? (
            <a
              href={issue.githubUrl}
              target="_blank"
              rel="noreferrer"
              className="btn-press rounded-xl p-2 transition-colors hover:bg-white/5"
              title="View on GitHub"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-4 w-4" style={{ color: "rgba(255, 255, 255, 0.5)" }} />
            </a>
          ) : (
            <Link
              href={href}
              className="btn-press rounded-xl p-2 transition-colors hover:bg-white/5"
              title="Open details"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-4 w-4" style={{ color: "rgba(255, 255, 255, 0.5)" }} />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
