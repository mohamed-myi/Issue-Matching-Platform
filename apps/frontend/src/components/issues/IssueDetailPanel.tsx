"use client";

import { useState } from "react";
import Link from "next/link";
import { X, ExternalLink, Github, MessageCircle, ThumbsUp, ThumbsDown, Bookmark } from "lucide-react";
import { cn } from "@/lib/utils";

export type IssueDetailModel = {
  nodeId: string;
  title: string;
  repoName: string;
  primaryLanguage: string | null;
  labels: string[];
  qScore: number | null;
  bodyPreview: string | null;
  commentsCount?: number;
  githubUrl?: string;
};

type IssueDetailPanelProps = {
  issue: IssueDetailModel;
  onClose: () => void;
  isBookmarked?: boolean;
  onToggleBookmark?: () => void;
  onViewSimilar?: () => void;
};

export function IssueDetailPanel({
  issue,
  onClose,
  isBookmarked = false,
  onToggleBookmark,
  onViewSimilar,
}: IssueDetailPanelProps) {
  const [isUpvoted, setIsUpvoted] = useState(false);
  const [isDownvoted, setIsDownvoted] = useState(false);

  function handleUpvote() {
    if (isUpvoted) {
      setIsUpvoted(false);
    } else {
      setIsUpvoted(true);
      setIsDownvoted(false);
    }
  }

  function handleDownvote() {
    if (isDownvoted) {
      setIsDownvoted(false);
    } else {
      setIsDownvoted(true);
      setIsUpvoted(false);
    }
  }

  function handleViewInGitHub() {
    const url = issue.githubUrl ?? `https://github.com/${issue.repoName}`;
    window.open(url, "_blank");
  }

  function handleViewRepo() {
    window.open(`https://github.com/${issue.repoName}`, "_blank");
  }

  const score = issue.qScore;
  const scoreColor =
    score !== null
      ? score >= 0.9
        ? "rgba(34, 197, 94, 0.95)"
        : score >= 0.8
          ? "rgba(99, 102, 241, 0.95)"
          : "rgba(234, 179, 8, 0.95)"
      : "rgba(138, 144, 178, 1)";

  return (
    <div
      className="w-[480px] flex-shrink-0 sticky top-24 rounded-xl overflow-hidden flex flex-col"
      style={{
        background: `linear-gradient(
          180deg,
          rgba(22, 26, 43, 0.95),
          rgba(18, 21, 35, 0.95)
        )`,
        border: "1px solid rgba(138, 92, 255, 0.1)",
        maxHeight: "calc(100vh - 8rem)",
        boxShadow: "0 0 1px rgba(255, 255, 255, 0.08) inset",
      }}
    >
      <div
        className="px-6 py-4 flex items-start justify-between gap-4 flex-shrink-0"
        style={{
          borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
        }}
      >
        <div className="flex-1 min-w-0">
          <h2
            className="text-[16px] font-semibold leading-snug mb-2"
            style={{
              color: "rgba(255, 255, 255, 0.95)",
              letterSpacing: "-0.01em",
            }}
          >
            {issue.title}
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-[12px] font-medium"
              style={{ color: "rgba(255, 255, 255, 0.45)" }}
            >
              {issue.repoName}
            </span>
            <span style={{ color: "rgba(255, 255, 255, 0.2)" }}>•</span>
            <span
              className="text-[12px] font-medium"
              style={{ color: "rgba(255, 255, 255, 0.55)" }}
            >
              {issue.primaryLanguage ?? "Unknown"}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="btn-press p-2 rounded-lg transition-all duration-200 hover:bg-white/5"
        >
          <X className="w-4 h-4" style={{ color: "rgba(255, 255, 255, 0.5)" }} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        {issue.labels.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap mb-5">
            {issue.labels.map((label) => (
              <span
                key={label}
                className="px-2.5 py-1 rounded-md text-[11px] font-medium"
                style={{
                  backgroundColor: "rgba(99, 102, 241, 0.12)",
                  color: "rgba(255, 255, 255, 0.75)",
                  border: "1px solid rgba(99, 102, 241, 0.25)",
                }}
              >
                {label}
              </span>
            ))}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <h3
              className="text-[13px] font-semibold mb-2"
              style={{ color: "rgba(255, 255, 255, 0.75)" }}
            >
              Description
            </h3>
            <p
              className="text-[13px] leading-relaxed"
              style={{ color: "rgba(255, 255, 255, 0.65)" }}
            >
              {issue.bodyPreview || "No description available."}
            </p>
          </div>

          <div className="space-y-2 pt-4">
            <div className="flex items-center justify-between">
              <span
                className="text-[12px] font-medium"
                style={{ color: "rgba(255, 255, 255, 0.45)" }}
              >
                Quality Score
              </span>
              <span
                className="text-[12px] font-bold"
                style={{ color: scoreColor }}
              >
                {score !== null ? `${(score * 100).toFixed(0)}/100` : "—"}
              </span>
            </div>
            {typeof issue.commentsCount === "number" && (
              <div className="flex items-center justify-between">
                <span
                  className="text-[12px] font-medium"
                  style={{ color: "rgba(255, 255, 255, 0.45)" }}
                >
                  Comments
                </span>
                <div className="flex items-center gap-1.5">
                  <MessageCircle
                    className="w-3 h-3"
                    style={{ color: "rgba(255, 255, 255, 0.45)" }}
                  />
                  <span
                    className="text-[12px] font-medium"
                    style={{ color: "rgba(255, 255, 255, 0.65)" }}
                  >
                    {issue.commentsCount}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="h-20" />
      </div>

      <div
        className="flex-shrink-0 px-6 py-4 flex items-center justify-between gap-4"
        style={{
          backgroundColor: "rgba(9, 9, 11, 0.85)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          borderTop: "1px solid rgba(255, 255, 255, 0.08)",
        }}
      >
        <div className="flex items-end gap-3 self-end">
          <div
            className="flex items-center rounded-lg overflow-hidden"
            style={{
              backgroundColor: "rgba(255, 255, 255, 0.05)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
            }}
          >
            <button
              type="button"
              onClick={handleUpvote}
              className="btn-press p-2 transition-all duration-200 hover:bg-white/5"
              style={{
                backgroundColor: isUpvoted ? "rgba(34, 197, 94, 0.15)" : "transparent",
              }}
            >
              <ThumbsUp
                className="w-4 h-4"
                style={{
                  color: isUpvoted ? "rgba(34, 197, 94, 0.95)" : "rgba(255, 255, 255, 0.55)",
                  fill: isUpvoted ? "rgba(34, 197, 94, 0.95)" : "none",
                }}
              />
            </button>
            <div
              style={{
                width: "1px",
                height: "20px",
                backgroundColor: "rgba(255, 255, 255, 0.08)",
              }}
            />
            <button
              type="button"
              onClick={handleDownvote}
              className="btn-press p-2 transition-all duration-200 hover:bg-white/5"
              style={{
                backgroundColor: isDownvoted ? "rgba(239, 68, 68, 0.15)" : "transparent",
              }}
            >
              <ThumbsDown
                className="w-4 h-4"
                style={{
                  color: isDownvoted ? "rgba(239, 68, 68, 0.95)" : "rgba(255, 255, 255, 0.55)",
                  fill: isDownvoted ? "rgba(239, 68, 68, 0.95)" : "none",
                }}
              />
            </button>
          </div>

          <button
            type="button"
            onClick={onToggleBookmark}
            disabled={!onToggleBookmark}
            className={cn(
              "btn-press p-2 rounded-lg transition-all duration-200",
              onToggleBookmark ? "hover:bg-white/5" : "opacity-50",
            )}
            style={{
              backgroundColor: isBookmarked ? "rgba(99, 102, 241, 0.15)" : "rgba(255, 255, 255, 0.05)",
              border: `1px solid ${isBookmarked ? "rgba(99, 102, 241, 0.3)" : "rgba(255, 255, 255, 0.08)"}`,
            }}
          >
            <Bookmark
              className="w-4 h-4"
              style={{
                color: isBookmarked ? "rgba(99, 102, 241, 0.95)" : "rgba(255, 255, 255, 0.55)",
                fill: isBookmarked ? "rgba(99, 102, 241, 0.95)" : "none",
              }}
            />
          </button>
        </div>

        <div className="flex flex-col gap-1.5 items-end min-w-[200px]">
          {onViewSimilar && (
            <button
              type="button"
              onClick={onViewSimilar}
              className="btn-press flex items-center justify-center gap-2 w-full min-w-[200px] px-5 py-2 rounded-lg text-[13px] font-semibold transition-all duration-200 hover:translate-y-[-1px]"
              style={{
                backgroundColor: "rgba(255, 255, 255, 0.05)",
                color: "rgba(255, 255, 255, 0.85)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
              }}
            >
              View similar issues
            </button>
          )}
          <button
            type="button"
            onClick={handleViewInGitHub}
            className="btn-press btn-glow flex items-center justify-center gap-2 w-full min-w-[200px] px-5 py-2 rounded-lg text-[13px] font-semibold transition-all duration-200 hover:translate-y-[-1px]"
            style={{
              backgroundColor: "rgba(255, 255, 255, 0.05)",
              color: "rgba(255, 255, 255, 0.85)",
              border: "1px solid rgba(138, 92, 255, 0.35)",
            }}
          >
            <ExternalLink className="w-4 h-4" style={{ color: "rgba(138, 92, 255, 0.95)" }} />
            View Issue
          </button>
          <button
            type="button"
            onClick={handleViewRepo}
            className="btn-press btn-glow flex items-center justify-center gap-2 w-full min-w-[200px] px-5 py-2 rounded-lg text-[13px] font-semibold transition-all duration-200 hover:translate-y-[-1px]"
            style={{
              backgroundColor: "rgba(255, 255, 255, 0.05)",
              color: "rgba(255, 255, 255, 0.85)",
              border: "1px solid rgba(138, 92, 255, 0.35)",
            }}
          >
            <Github className="w-4 h-4" style={{ color: "rgba(138, 92, 255, 0.95)" }} />
            View Repository
          </button>
        </div>
      </div>
    </div>
  );
}
