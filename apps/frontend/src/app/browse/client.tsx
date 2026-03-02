"use client";

import { useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { IssueListPageClientShell } from "@/components/issues/IssueListPageClientShell";
import { type IssueListItemModel } from "@/components/issues/IssueListItem";
import {
  useSearch,
  useTrending,
  useMe,
  useLogSearchInteraction,
} from "@/lib/api/hooks";
import type { AuthMeResponse, SearchResponse, TrendingResponse } from "@/lib/api/types";

type BrowseClientProps = {
  initialMe?: AuthMeResponse | null;
  initialSearchPage?: SearchResponse | null;
  initialTrendingPage?: TrendingResponse | null;
};

export default function BrowseClient({
  initialMe = null,
  initialSearchPage = null,
  initialTrendingPage = null,
}: BrowseClientProps) {
  const sp = useSearchParams();
  const router = useRouter();

  const q = sp.get("q") ?? "";
  const lang = sp.get("lang") ?? null;
  const label = sp.get("label") ?? null;
  const repo = sp.get("repo") ?? null;

  const meQuery = useMe(initialMe);

  const filters = useMemo(
    () => ({
      languages: lang ? [lang] : undefined,
      labels: label ? [label] : undefined,
      repos: repo ? [repo] : undefined,
    }),
    [lang, label, repo]
  );

  const searchQuery = useSearch({
    query: q,
    filters,
    pageSize: 20,
    enabled: q.trim().length > 0,
    initialPage: q.trim().length > 0 ? (initialSearchPage ?? undefined) : undefined,
  });

  const trendingQuery = useTrending(
    20,
    filters,
    q.trim().length === 0 ? (initialTrendingPage ?? undefined) : undefined,
  );
  const logSearchInteraction = useLogSearchInteraction();

  const activeQuery = q.trim().length > 0 ? searchQuery : trendingQuery;

  const searchContextByNodeId = useMemo(() => {
    const map = new Map<string, { searchId: string; position: number }>();
    if (q.trim().length === 0) return map;
    const pages = searchQuery.data?.pages ?? [];
    for (const page of pages) {
      for (const [idx, result] of page.results.entries()) {
        map.set(result.node_id, {
          searchId: page.search_id,
          position: (page.page - 1) * page.page_size + idx + 1,
        });
      }
    }
    return map;
  }, [q, searchQuery.data]);

  const items = useMemo(() => {
    const pages = activeQuery.data?.pages ?? [];
    const allResults = pages.flatMap((page) => page.results);

    return allResults.map<IssueListItemModel>((r) => {
      return {
        nodeId: r.node_id,
        title: r.title,
        repoName: r.repo_name,
        primaryLanguage: r.primary_language,
        labels: r.labels,
        qScore: r.q_score,
        createdAt: r.github_created_at,
        bodyPreview: r.body_preview,
        githubUrl: r.github_url ?? null,
      };
    });
  }, [activeQuery.data]);
  const canSave = Boolean(meQuery.data);
  const total = activeQuery.data?.pages[0]?.total ?? 0;

  return (
    <IssueListPageClientShell
      activeTab="browse"
      title="Browse"
      subtitle={
        q.trim().length > 0 ? `${total} results for "${q}"` : "Search issues or explore trending ones"
      }
      viewerEmail={meQuery.data?.email}
      items={items}
      isLoading={activeQuery.isLoading}
      emptyStateTitle="No issues match your query"
      hasNextPage={activeQuery.hasNextPage}
      isFetchingNextPage={activeQuery.isFetchingNextPage}
      fetchNextPage={activeQuery.fetchNextPage}
      canSave={canSave}
      disableListSaveWhenCannotSave
      onRequireLogin={() => router.push("/login")}
      onIssueSelected={(issue) => {
        if (q.trim().length === 0) return;
        const ctx = searchContextByNodeId.get(issue.nodeId);
        if (!ctx) return;
        logSearchInteraction.mutate({
          search_id: ctx.searchId,
          selected_node_id: issue.nodeId,
          position: ctx.position,
        });
      }}
    />
  );
}
