"use client";

import { useMemo, useState, useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { EmptyState } from "@/components/common/EmptyState";
import { IssueListPageClientShell } from "@/components/issues/IssueListPageClientShell";
import { type IssueListItemModel } from "@/components/issues/IssueListItem";
import { ProfileCTA } from "@/components/issues/ProfileCTA";
import { getApiErrorMessage } from "@/lib/api/client";
import {
  useSearch,
  useFeed,
  useLogRecommendationEvents,
  useLogSearchInteraction,
} from "@/lib/api/hooks";
import { useAuthGuard } from "@/lib/hooks/use-auth-guard";
import type { AuthMeResponse, FeedResponse, SearchResponse } from "@/lib/api/types";

type ForYouClientProps = {
  initialMe?: AuthMeResponse | null;
  initialSearchPage?: SearchResponse | null;
  initialFeedPage?: FeedResponse | null;
};

export default function ForYouClient({
  initialMe = null,
  initialSearchPage = null,
  initialFeedPage = null,
}: ForYouClientProps) {
  const sp = useSearchParams();

  const q = sp.get("q") ?? "";
  const lang = sp.get("lang") ?? null;
  const label = sp.get("label") ?? null;
  const repo = sp.get("repo") ?? null;

  const { me: meQuery, isRedirecting } = useAuthGuard(initialMe);

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

  const feedQuery = useFeed(
    20,
    filters,
    q.trim().length === 0 ? (initialFeedPage ?? undefined) : undefined,
  );
  const logRecommendationEvents = useLogRecommendationEvents();
  const logSearchInteraction = useLogSearchInteraction();
  const loggedRecommendationBatchIds = useRef<Set<string>>(new Set());

  const activeQuery = q.trim().length > 0 ? searchQuery : feedQuery;

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

  const recommendationContextByNodeId = useMemo(() => {
    const map = new Map<string, { recommendationBatchId: string; position: number }>();
    const pages = feedQuery.data?.pages ?? [];
    for (const page of pages) {
      if (!page.recommendation_batch_id) continue;
      for (const [idx, result] of page.results.entries()) {
        map.set(result.node_id, {
          recommendationBatchId: page.recommendation_batch_id,
          position: idx + 1,
        });
      }
    }
    return map;
  }, [feedQuery.data]);

  useEffect(() => {
    if (q.trim().length > 0) return;

    const pages = feedQuery.data?.pages ?? [];
    for (const page of pages) {
      const batchId = page.recommendation_batch_id;
      if (!batchId || loggedRecommendationBatchIds.current.has(batchId)) {
        continue;
      }

      const events = page.results.map((result, idx) => ({
        event_id: crypto.randomUUID(),
        event_type: "impression" as const,
        issue_node_id: result.node_id,
        position: idx + 1,
        surface: "for-you",
      }));
      if (events.length === 0) continue;

      loggedRecommendationBatchIds.current.add(batchId);
      logRecommendationEvents.mutate(
        {
          recommendation_batch_id: batchId,
          events,
        },
        {
          onError: () => {
            loggedRecommendationBatchIds.current.delete(batchId);
          },
        },
      );
    }
  }, [q, feedQuery.data, logRecommendationEvents]);

  const items = useMemo(() => {
    if (q.trim().length > 0) {
      const searchPages = searchQuery.data?.pages ?? [];
      const allResults = searchPages.flatMap((page) => page.results);
      return allResults.map<IssueListItemModel>((r) => ({
        nodeId: r.node_id,
        title: r.title,
        repoName: r.repo_name,
        primaryLanguage: r.primary_language,
        labels: r.labels,
        qScore: r.q_score,
        createdAt: r.github_created_at,
        bodyPreview: r.body_preview,
        whyThis: null,
        githubUrl: r.github_url ?? null,
      }));
    }

    const feedPages = feedQuery.data?.pages ?? [];
    const allResults = feedPages.flatMap((page) => page.results);
    return allResults.map<IssueListItemModel>((r) => ({
      nodeId: r.node_id,
      title: r.title,
      repoName: r.repo_name,
      primaryLanguage: r.primary_language,
      labels: r.labels,
      qScore: r.q_score,
      createdAt: r.github_created_at,
      bodyPreview: r.body_preview,
      whyThis: r.why_this ?? null,
      githubUrl: r.github_url ?? null,
    }));
  }, [q, searchQuery.data, feedQuery.data]);

  const isPersonalized = q.trim().length === 0 ? (feedQuery.data?.pages[0]?.is_personalized ?? false) : false;
  const total = activeQuery.data?.pages[0]?.total ?? 0;

  if (isRedirecting) return null;

  return (
    <IssueListPageClientShell
      activeTab="for-you"
      title={q.trim().length > 0 ? "Search Results" : "For You"}
      subtitle={
        q.trim().length > 0
          ? `${total} results for "${q}"`
          : isPersonalized
            ? "Issues tailored to your skills and interests"
            : "Complete your profile for personalized recommendations"
      }
      viewerEmail={meQuery.data?.email}
      items={items}
      isLoading={activeQuery.isLoading}
      isError={activeQuery.isError}
      errorState={
        <EmptyState
          title="Sign in required"
          description={getApiErrorMessage(activeQuery.error) + " — go to Login to continue."}
        />
      }
      emptyStateTitle={q.trim().length > 0 ? "No issues match your query" : "No recommendations match your filters"}
      hasNextPage={activeQuery.hasNextPage}
      isFetchingNextPage={activeQuery.isFetchingNextPage}
      fetchNextPage={activeQuery.fetchNextPage}
      canSave
      beforeListContent={
        q.trim().length === 0 && !isPersonalized && !feedQuery.isLoading && !feedQuery.isError ? (
          <ProfileCTA />
        ) : null
      }
      onIssueSelected={(issue) => {
        if (q.trim().length > 0) {
          const searchCtx = searchContextByNodeId.get(issue.nodeId);
          if (!searchCtx) return;
          logSearchInteraction.mutate({
            search_id: searchCtx.searchId,
            selected_node_id: issue.nodeId,
            position: searchCtx.position,
          });
          return;
        }

        const recommendationCtx = recommendationContextByNodeId.get(issue.nodeId);
        if (!recommendationCtx) return;

        logRecommendationEvents.mutate({
          recommendation_batch_id: recommendationCtx.recommendationBatchId,
          events: [
            {
              event_id: crypto.randomUUID(),
              event_type: "click",
              issue_node_id: issue.nodeId,
              position: recommendationCtx.position,
              surface: "for-you",
            },
          ],
        });
      }}
    />
  );
}
