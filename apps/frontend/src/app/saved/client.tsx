"use client";

import type { Route } from "next";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useInfiniteQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState } from "@/components/common/EmptyState";
import { SkeletonList } from "@/components/common/SkeletonList";
import { LoadMoreButton } from "@/components/common/LoadMoreButton";
import { IssueListItem, type IssueListItemModel } from "@/components/issues/IssueListItem";
import { listBookmarks } from "@/lib/api/endpoints";
import { useDeleteBookmark, usePatchBookmark } from "@/lib/api/hooks";
import { getApiErrorMessage } from "@/lib/api/client";
import { useAuthGuard } from "@/lib/hooks/use-auth-guard";
import { cn } from "@/lib/utils";

type FilterTab = "all" | "unresolved" | "resolved";

function parseRepoFromGithubUrl(url: string): string | null {
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    if (parts.length >= 2) {
      return `${parts[0]}/${parts[1]}`;
    }
    return null;
  } catch {
    return null;
  }
}

function matchesText(haystack: string, needle: string) {
  return haystack.toLowerCase().includes(needle.toLowerCase());
}

export default function SavedClient() {
  const PAGE_SIZE = 50;
  const sp = useSearchParams();

  const q = sp.get("q") ?? "";
  const repo = sp.get("repo") ?? null;

  const [filterTab, setFilterTab] = useState<FilterTab>("all");

  const { isRedirecting } = useAuthGuard();
  const bookmarksQuery = useInfiniteQuery({
    queryKey: ["bookmarks", "saved", PAGE_SIZE],
    queryFn: ({ pageParam }) => listBookmarks(pageParam, PAGE_SIZE),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.page + 1 : undefined),
    staleTime: 1000 * 10,
  });
  const deleteBookmarkMutation = useDeleteBookmark();
  const patchBookmarkMutation = usePatchBookmark();

  const allBookmarks = useMemo(
    () => bookmarksQuery.data?.pages.flatMap((pageData) => pageData.results) ?? [],
    [bookmarksQuery.data],
  );

  const items = useMemo(() => {
    return allBookmarks
      .filter((b) => {
        if (filterTab === "resolved") return b.is_resolved;
        if (filterTab === "unresolved") return !b.is_resolved;
        return true;
      })
      .filter((b) => (repo ? parseRepoFromGithubUrl(b.github_url) === repo : true))
      .filter((b) => (q ? matchesText(b.title_snapshot, q) || matchesText(b.github_url, q) : true))
      .map<{ bookmarkId: string; issue: IssueListItemModel; isResolved: boolean }>((b) => ({
        bookmarkId: b.id,
        isResolved: b.is_resolved,
        issue: {
          nodeId: b.issue_node_id,
          title: b.title_snapshot,
          repoName: parseRepoFromGithubUrl(b.github_url) ?? "unknown/unknown",
          primaryLanguage: null,
          labels: b.is_resolved ? ["resolved"] : [],
          qScore: null,
          createdAt: b.created_at,
          bodyPreview: b.body_snapshot,
          githubUrl: b.github_url,
        },
      }));
  }, [allBookmarks, q, repo, filterTab]);

  const totalAll = allBookmarks.length;
  const totalResolved = allBookmarks.filter((b) => b.is_resolved).length;
  const totalUnresolved = allBookmarks.filter((b) => !b.is_resolved).length;

  const hasMore = bookmarksQuery.hasNextPage ?? false;
  const total = bookmarksQuery.data?.pages[0]?.total ?? 0;
  const remaining = Math.max(0, total - allBookmarks.length);

  function handleLoadMore() {
    void bookmarksQuery.fetchNextPage();
  }

  if (isRedirecting) return null;

  return (
    <AppShell activeTab={null}>
      <div className="mb-6">
        <h1
          className="text-xl font-semibold tracking-tight"
          style={{ color: "rgba(230, 233, 242, 0.95)" }}
        >
          Saved Issues
        </h1>
        <p className="mt-1 text-sm" style={{ color: "rgba(138, 144, 178, 1)" }}>
          Issues you&apos;ve bookmarked for later
        </p>
      </div>

      <div className="mb-6 flex items-center gap-2">
        <FilterTabButton
          active={filterTab === "all"}
          onClick={() => setFilterTab("all")}
          count={totalAll}
        >
          All
        </FilterTabButton>
        <FilterTabButton
          active={filterTab === "unresolved"}
          onClick={() => setFilterTab("unresolved")}
          count={totalUnresolved}
        >
          Unresolved
        </FilterTabButton>
        <FilterTabButton
          active={filterTab === "resolved"}
          onClick={() => setFilterTab("resolved")}
          count={totalResolved}
        >
          Resolved
        </FilterTabButton>
      </div>

      {bookmarksQuery.isLoading ? (
        <SkeletonList rows={10} />
      ) : bookmarksQuery.isError ? (
        <EmptyState
          title="Sign in required"
          description={getApiErrorMessage(bookmarksQuery.error) + " — go to Login to continue."}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="No saved issues"
          description={
            filterTab === "all"
              ? "Save issues from Browse or For You to see them here."
              : `No ${filterTab} issues found.`
          }
        />
      ) : (
        <>
          <div
            className="rounded-2xl overflow-hidden"
            style={{
              backgroundColor: "rgba(17, 20, 32, 0.5)",
              border: "1px solid rgba(255, 255, 255, 0.04)",
            }}
          >
            {items.map(({ issue, bookmarkId, isResolved }) => (
              <div
                key={bookmarkId}
                style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)" }}
              >
                <IssueListItem
                  href={`/saved/${bookmarkId}` as Route}
                  issue={issue}
                  isSaved
                  onToggleSaved={() => deleteBookmarkMutation.mutate(bookmarkId)}
                />
                <div className="flex items-center gap-2 px-6 py-3">
                  <button
                    type="button"
                    className="btn-press rounded-xl border px-3 py-1.5 text-xs font-medium hover:bg-white/5 transition-colors"
                    style={{ borderColor: "rgba(255,255,255,0.08)" }}
                    onClick={() =>
                      patchBookmarkMutation.mutate({ bookmarkId, isResolved: !isResolved })
                    }
                    disabled={patchBookmarkMutation.isPending}
                  >
                    {isResolved ? "Mark unresolved" : "Mark resolved"}
                  </button>
                  <button
                    type="button"
                    className="btn-press rounded-xl border px-3 py-1.5 text-xs font-medium hover:bg-white/5 transition-colors"
                    style={{ borderColor: "rgba(255,255,255,0.08)" }}
                    onClick={() => deleteBookmarkMutation.mutate(bookmarkId)}
                    disabled={deleteBookmarkMutation.isPending}
                  >
                    Remove
                  </button>
                  <Link
                    href={`/saved/${bookmarkId}` as Route}
                    className="btn-press ml-auto text-xs underline underline-offset-2 hover:text-white/80 transition-colors"
                    style={{ color: "rgba(138,144,178,1)" }}
                  >
                    View notes
                  </Link>
                </div>
              </div>
            ))}
          </div>

          {hasMore && (
            <LoadMoreButton
              onClick={handleLoadMore}
              isLoading={bookmarksQuery.isFetchingNextPage}
              remaining={remaining}
            />
          )}
        </>
      )}
    </AppShell>
  );
}

function FilterTabButton(props: {
  active: boolean;
  onClick: () => void;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      className={cn(
        "btn-press flex items-center gap-2 rounded-xl px-4 py-2 text-[13px] font-medium transition-all duration-200 hover:bg-white/10",
      )}
      style={{
        backgroundColor: props.active ? "rgba(99, 102, 241, 0.15)" : "rgba(255, 255, 255, 0.03)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        color: props.active ? "rgba(255, 255, 255, 0.95)" : "rgba(255, 255, 255, 0.60)",
      }}
    >
      {props.children}
      <span
        className="px-1.5 py-0.5 rounded-md text-[11px] font-semibold"
        style={{
          backgroundColor: props.active ? "rgba(138, 92, 255, 0.15)" : "rgba(255, 255, 255, 0.05)",
          color: props.active ? "#C7BFFF" : "rgba(255, 255, 255, 0.50)",
        }}
      >
        {props.count}
      </span>
    </button>
  );
}
