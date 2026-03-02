"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { EmptyState } from "@/components/common/EmptyState";
import { SkeletonList } from "@/components/common/SkeletonList";
import { AppShell } from "@/components/layout/AppShell";
import { useBookmarkCheck, useCreateBookmark, useDeleteBookmark } from "@/lib/api/hooks";
import { useInfiniteScroll } from "@/lib/hooks/use-infinite-scroll";
import { IssueDetailPanel, type IssueDetailModel } from "./IssueDetailPanel";
import { IssueListItem, type IssueListItemModel } from "./IssueListItem";

type ActiveTab = "browse" | "dashboard" | "for-you";

type IssueListPageClientShellProps = {
  activeTab: ActiveTab;
  title: string;
  subtitle: string;
  viewerEmail?: string | null;
  items: IssueListItemModel[];
  isLoading: boolean;
  isError?: boolean;
  errorState?: ReactNode;
  emptyStateTitle: string;
  emptyStateDescription?: string;
  hasNextPage: boolean | undefined;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  canSave?: boolean;
  disableListSaveWhenCannotSave?: boolean;
  onRequireLogin?: () => void;
  onIssueSelected?: (issue: IssueListItemModel) => void;
  beforeListContent?: ReactNode;
};

function toIssueDetailModel(issue: IssueListItemModel): IssueDetailModel {
  return {
    nodeId: issue.nodeId,
    title: issue.title,
    repoName: issue.repoName,
    primaryLanguage: issue.primaryLanguage,
    labels: issue.labels,
    qScore: issue.qScore,
    bodyPreview: issue.bodyPreview ?? null,
    githubUrl: issue.githubUrl ?? undefined,
  };
}

export function IssueListPageClientShell({
  activeTab,
  title,
  subtitle,
  viewerEmail = null,
  items,
  isLoading,
  isError = false,
  errorState,
  emptyStateTitle,
  emptyStateDescription,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  canSave = true,
  disableListSaveWhenCannotSave = false,
  onRequireLogin,
  onIssueSelected,
  beforeListContent,
}: IssueListPageClientShellProps) {
  const router = useRouter();
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);

  const issueNodeIds = useMemo(() => items.map((i) => i.nodeId), [items]);
  const bookmarkCheckQuery = useBookmarkCheck(canSave ? issueNodeIds : []);
  const createBookmark = useCreateBookmark();
  const deleteBookmarkMutation = useDeleteBookmark();

  const bookmarksMap = useMemo(
    () => bookmarkCheckQuery.data?.bookmarks ?? {},
    [bookmarkCheckQuery.data?.bookmarks],
  );

  const handleToggleBookmark = useCallback(
    (issue: IssueListItemModel) => {
      if (!canSave) {
        onRequireLogin?.();
        return;
      }

      const bookmarkId = bookmarksMap[issue.nodeId];
      if (bookmarkId) {
        deleteBookmarkMutation.mutate(bookmarkId);
      } else {
        createBookmark.mutate({
          issue_node_id: issue.nodeId,
          github_url: issue.githubUrl ?? `https://github.com/${issue.repoName}`,
          title_snapshot: issue.title,
          body_snapshot: issue.bodyPreview ?? "",
        });
      }
    },
    [bookmarksMap, canSave, createBookmark, deleteBookmarkMutation, onRequireLogin],
  );

  const selectedIssue = useMemo(() => {
    if (!selectedIssueId) return null;
    const found = items.find((item) => item.nodeId === selectedIssueId);
    return found ? toIssueDetailModel(found) : null;
  }, [items, selectedIssueId]);

  const sentinelRef = useInfiniteScroll({
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  });

  const renderList = !isLoading && !isError && items.length > 0;

  return (
    <AppShell activeTab={activeTab}>
      <div className="flex gap-6">
        <div className="flex-1 min-w-0">
          <div className="mb-6">
            <div className="flex items-center justify-between">
              <div>
                <h1
                  className="text-xl font-semibold tracking-tight"
                  style={{ color: "rgba(230, 233, 242, 0.95)" }}
                >
                  {title}
                </h1>
                <p className="mt-1 text-sm" style={{ color: "rgba(138, 144, 178, 1)" }}>
                  {subtitle}
                </p>
              </div>
              <div className="text-[12px] font-medium" style={{ color: "#64748B" }}>
                {viewerEmail ? `Signed in as ${viewerEmail}` : "Guest"}
              </div>
            </div>
          </div>

          {beforeListContent}

          {isLoading ? (
            <SkeletonList rows={10} />
          ) : isError && errorState ? (
            errorState
          ) : items.length === 0 ? (
            <EmptyState title={emptyStateTitle} description={emptyStateDescription} />
          ) : (
            <>
              <div
                className="rounded-2xl overflow-hidden"
                style={{
                  backgroundColor: "rgba(17, 20, 32, 0.5)",
                  border: "1px solid rgba(255, 255, 255, 0.04)",
                }}
              >
                {items.map((issue) => (
                  <div
                    key={issue.nodeId}
                    onClick={() => {
                      setSelectedIssueId(issue.nodeId);
                      onIssueSelected?.(issue);
                    }}
                    className="btn-press cursor-pointer transition-colors hover:bg-white/[0.02]"
                    style={{
                      backgroundColor:
                        selectedIssueId === issue.nodeId ? "rgba(138, 92, 255, 0.08)" : undefined,
                      boxShadow:
                        selectedIssueId === issue.nodeId
                          ? "inset 2px 0 0 rgba(138, 92, 255, 0.6)"
                          : "none",
                    }}
                  >
                    <IssueListItem
                      issue={issue}
                      href={`/issues/${issue.nodeId}` as Route}
                      isSaved={!!bookmarksMap[issue.nodeId]}
                      onToggleSaved={
                        !canSave && disableListSaveWhenCannotSave
                          ? undefined
                          : () => handleToggleBookmark(issue)
                      }
                    />
                  </div>
                ))}
              </div>

              {hasNextPage && renderList ? (
                <div ref={sentinelRef} className="py-8 flex justify-center">
                  <div className="animate-spin h-6 w-6 border-2 border-purple-500 border-t-transparent rounded-full" />
                </div>
              ) : null}
            </>
          )}
        </div>

        {selectedIssue ? (
          <IssueDetailPanel
            issue={selectedIssue}
            onClose={() => setSelectedIssueId(null)}
            isBookmarked={!!bookmarksMap[selectedIssue.nodeId]}
            onToggleBookmark={() => {
              const found = items.find((item) => item.nodeId === selectedIssue.nodeId);
              if (found) handleToggleBookmark(found);
            }}
            onViewSimilar={() => router.push(`/issues/${selectedIssue.nodeId}`)}
          />
        ) : null}
      </div>
    </AppShell>
  );
}


export type { IssueListPageClientShellProps };
