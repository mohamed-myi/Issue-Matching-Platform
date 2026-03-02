import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchPublicStats,
  fetchTrending,
  fetchFeed,
  logRecommendationEvents,
  searchIssues,
  logSearchInteraction,
  fetchIssue,
  fetchSimilarIssues,
  fetchRepositories,
  fetchLanguages,
  fetchStackAreas,
  fetchMe,
  listBookmarks,
  getBookmark,
  createBookmark,
  deleteBookmark,
  patchBookmark,
  batchBookmarkCheck,
  listNotes,
  addNote,
  updateNote,
  deleteNote,
  fetchProfile,
  fetchProfileOnboarding,
  fetchPreferences,
  patchPreferences,
  fetchLinkedAccounts,
  fetchSessions,
  logout,
  logoutAll,
  deleteAccount,
  unlinkAccount,
  startOnboarding,
  skipOnboarding,
  completeOnboarding,
  saveOnboardingStep,
  uploadResume,
  initiateGithubFetch,
} from "./endpoints";
import type {
  AuthMeResponse,
  FeedResponse,
  SearchRequest,
  SearchResponse,
  ProfilePreferences,
  OnboardingStep,
  RecommendationEventsRequest,
  SearchInteractionInput,
  TrendingResponse,
} from "./types";

type QueryRefetchStateLike = {
  state: {
    data?: {
      is_calculating?: boolean;
    };
  };
};

type QueryPollingOptions = {
  refetchInterval?:
  | number
  | false
  | ((query: QueryRefetchStateLike) => number | false | undefined);
};

type MutationLifecycleCallbacks = {
  onSuccess?: () => void | Promise<void>;
  onError?: (error: unknown) => void | Promise<void>;
};

export function usePublicStats() {
  return useQuery({
    queryKey: ["public", "stats"],
    queryFn: fetchPublicStats,
    staleTime: 1000 * 60,
  });
}

export function useTrending(
  pageSize = 20,
  filters?: { languages?: string[]; labels?: string[]; repos?: string[] },
  initialPage?: TrendingResponse,
) {
  return useInfiniteQuery({
    queryKey: ["feed", "trending", pageSize, filters],
    queryFn: ({ pageParam }) => fetchTrending(pageParam, pageSize, filters),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.page + 1 : undefined),
    staleTime: 1000 * 30,
    initialData: initialPage
      ? {
        pages: [initialPage],
        pageParams: [1],
      }
      : undefined,
  });
}

export function useFeed(
  pageSize = 20,
  filters?: { languages?: string[]; labels?: string[]; repos?: string[] },
  initialPage?: FeedResponse,
) {
  return useInfiniteQuery({
    queryKey: ["feed", pageSize, filters],
    queryFn: ({ pageParam }) => fetchFeed(pageParam, pageSize, filters),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.page + 1 : undefined),
    staleTime: 1000 * 30,
    initialData: initialPage
      ? {
        pages: [initialPage],
        pageParams: [1],
      }
      : undefined,
  });
}

export function useSearch(params: {
  query: string;
  filters?: SearchRequest["filters"];
  pageSize?: number;
  enabled?: boolean;
  initialPage?: SearchResponse;
}) {
  const { query, filters, pageSize = 20, enabled = true, initialPage } = params;

  return useInfiniteQuery({
    queryKey: ["search", query, filters, pageSize],
    queryFn: ({ pageParam }) =>
      searchIssues({
        query,
        filters,
        page: pageParam,
        page_size: pageSize,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.page + 1 : undefined),
    enabled: enabled && query.trim().length > 0,
    retry: false,
    staleTime: 1000 * 30,
    initialData: initialPage
      ? {
        pages: [initialPage],
        pageParams: [1],
      }
      : undefined,
  });
}

export function useLogRecommendationEvents() {
  return useMutation({
    mutationFn: (payload: RecommendationEventsRequest) => logRecommendationEvents(payload),
  });
}

export function useLogSearchInteraction() {
  return useMutation({
    mutationFn: (payload: SearchInteractionInput) => logSearchInteraction(payload),
  });
}

export function useIssue(nodeId: string | null) {
  return useQuery({
    queryKey: ["issue", nodeId],
    queryFn: () => fetchIssue(nodeId!),
    enabled: !!nodeId,
    staleTime: 1000 * 60 * 5,
  });
}

export function useSimilarIssues(nodeId: string | null, limit = 5) {
  return useQuery({
    queryKey: ["issue", nodeId, "similar", limit],
    queryFn: () => fetchSimilarIssues(nodeId!, limit),
    enabled: !!nodeId,
    staleTime: 1000 * 60,
  });
}

export function useRepositories(params: { q?: string; language?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ["repositories", params],
    queryFn: () => fetchRepositories(params),
    staleTime: 1000 * 60 * 5,
  });
}

export function useLanguages() {
  return useQuery({
    queryKey: ["taxonomy", "languages"],
    queryFn: fetchLanguages,
    staleTime: 1000 * 60 * 60,
  });
}

export function useStackAreas() {
  return useQuery({
    queryKey: ["taxonomy", "stack-areas"],
    queryFn: fetchStackAreas,
    staleTime: 1000 * 60 * 60,
  });
}

export function useBookmarks(page = 1, pageSize = 20) {
  return useQuery({
    queryKey: ["bookmarks", page, pageSize],
    queryFn: () => listBookmarks(page, pageSize),
    staleTime: 1000 * 10,
  });
}

export function useBookmark(bookmarkId: string | null) {
  return useQuery({
    queryKey: ["bookmark", bookmarkId],
    queryFn: () => getBookmark(bookmarkId!),
    enabled: !!bookmarkId,
    staleTime: 1000 * 60,
  });
}

export function useBookmarkCheck(issueNodeIds: string[]) {
  return useQuery({
    queryKey: ["bookmarks", "check", issueNodeIds],
    queryFn: () => batchBookmarkCheck(issueNodeIds),
    enabled: issueNodeIds.length > 0,
    staleTime: 1000 * 30,
  });
}

export function useCreateBookmark() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: createBookmark,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bookmarks"] });
    },
  });
}

export function useDeleteBookmark() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: deleteBookmark,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bookmarks"] });
    },
  });
}

export function usePatchBookmark() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ bookmarkId, isResolved }: { bookmarkId: string; isResolved: boolean }) =>
      patchBookmark(bookmarkId, { is_resolved: isResolved }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bookmarks"] });
    },
  });
}

export function useNotes(bookmarkId: string | null) {
  return useQuery({
    queryKey: ["bookmark", bookmarkId, "notes"],
    queryFn: () => listNotes(bookmarkId!),
    enabled: !!bookmarkId,
    staleTime: 1000 * 30,
  });
}

export function useAddNote() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ bookmarkId, content }: { bookmarkId: string; content: string }) =>
      addNote(bookmarkId, content),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ["bookmark", variables.bookmarkId, "notes"] });
    },
  });
}

export function useUpdateNote() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ noteId, content }: { noteId: string; content: string }) =>
      updateNote(noteId, content),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bookmark"] });
    },
  });
}

export function useDeleteNote() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: deleteNote,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bookmark"] });
    },
  });
}

/** Server-injected hint from layout.tsx (set before React hydrates). */
function hasSessionHint(): boolean {
  if (typeof window !== "undefined" && "__HAS_SESSION__" in window) {
    return (window as unknown as { __HAS_SESSION__: boolean }).__HAS_SESSION__ === true;
  }
  return true; // SSR / fallback: assume session might exist
}

export function useMe(initialData?: AuthMeResponse | null) {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: fetchMe,
    retry: false,
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    enabled: hasSessionHint(),
    initialData: initialData ?? undefined,
  });
}

export function useSessions() {
  return useQuery({
    queryKey: ["auth", "sessions"],
    queryFn: fetchSessions,
    retry: false,
    staleTime: 1000 * 30,
  });
}

export function useLinkedAccounts() {
  return useQuery({
    queryKey: ["auth", "linked-accounts"],
    queryFn: fetchLinkedAccounts,
    retry: false,
    staleTime: 1000 * 60,
  });
}

export function useProfile(options?: QueryPollingOptions) {
  return useQuery({
    queryKey: ["profile"],
    queryFn: fetchProfile,
    retry: false,
    staleTime: 1000 * 30,
    refetchInterval: options?.refetchInterval,
  });
}

export function useOnboarding(options?: QueryPollingOptions) {
  return useQuery({
    queryKey: ["profile", "onboarding"],
    queryFn: fetchProfileOnboarding,
    retry: false,
    staleTime: 1000 * 30,
    refetchInterval: options?.refetchInterval,
  });
}

export function usePreferences() {
  return useQuery({
    queryKey: ["profile", "preferences"],
    queryFn: fetchPreferences,
    retry: false,
    staleTime: 1000 * 30,
  });
}

export function usePatchPreferences(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: Partial<ProfilePreferences>) => patchPreferences(payload),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["profile", "preferences"] });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useStartOnboarding(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: startOnboarding,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["profile", "onboarding"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useSkipOnboarding(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: skipOnboarding,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["profile", "onboarding"] });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useCompleteOnboarding(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: completeOnboarding,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["profile", "onboarding"] });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useSaveOnboardingStep(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ step, payload }: { step: OnboardingStep; payload: unknown }) =>
      saveOnboardingStep(step, payload),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["profile", "onboarding"] });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useUploadResume(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => uploadResume(file),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["profile", "onboarding"] });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useInitiateGithubFetch(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: initiateGithubFetch,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["profile", "onboarding"] });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useLogout(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["auth", "me"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useLogoutAll(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: logoutAll,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["auth", "me"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useDeleteAccount(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: deleteAccount,
    onSuccess: async () => {
      await qc.invalidateQueries();
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}

export function useUnlinkAccount(callbacks?: MutationLifecycleCallbacks) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (provider: string) => unlinkAccount(provider),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["auth", "linked-accounts"] });
      await qc.invalidateQueries({ queryKey: ["auth", "me"] });
      await callbacks?.onSuccess?.();
    },
    onError: async (error) => {
      await callbacks?.onError?.(error);
    },
  });
}
