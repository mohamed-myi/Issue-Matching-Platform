import { api } from "./client";
import type {
  AuthMeResponse,
  Bookmark,
  BookmarkBatchCheckResponse,
  BookmarksListResponse,
  FeedResponse,
  RecommendationEventsRequest,
  SearchInteractionInput,
  IssueDetailResponse,
  LinkedAccountsResponse,
  NotesListResponse,
  OnboardingStep,
  OnboardingStepResponse,
  OAuthProvider,
  GitHubAcceptedResponse,
  GitHubDataResponse,
  ProfileOnboardingResponse,
  ProfilePreferences,
  ProfilePreferencesResponse,
  ProfileResponse,
  PublicStatsResponse,
  RepositoriesResponse,
  SearchRequest,
  SearchResponse,
  SessionsResponse,
  SimilarIssuesResponse,
  ResumeUploadAcceptedResponse,
  ResumeDataResponse,
  TaxonomyLanguagesResponse,
  TaxonomyStackAreasResponse,
  TrendingResponse,
} from "./types";

type FeedFilters = {
  languages?: string[];
  labels?: string[];
  repos?: string[];
};

function buildFeedFilterParams(
  page: number,
  pageSize: number,
  filters?: FeedFilters,
): Record<string, number | string[]> {
  const params: Record<string, number | string[]> = {
    page,
    page_size: pageSize,
  };

  if (filters?.languages?.length) params.languages = filters.languages;
  if (filters?.labels?.length) params.labels = filters.labels;
  if (filters?.repos?.length) params.repos = filters.repos;

  return params;
}

export async function fetchPublicStats() {
  const { data } = await api.get<PublicStatsResponse>("/stats");
  return data;
}

export async function fetchTrending(
  page = 1,
  pageSize = 20,
  filters?: FeedFilters
) {
  const { data } = await api.get<TrendingResponse>("/feed/trending", {
    params: buildFeedFilterParams(page, pageSize, filters),
  });
  return data;
}

export async function fetchFeed(
  page = 1,
  pageSize = 20,
  filters?: FeedFilters
) {
  const { data } = await api.get<FeedResponse>("/feed", {
    params: buildFeedFilterParams(page, pageSize, filters),
  });
  return data;
}

export async function logRecommendationEvents(body: RecommendationEventsRequest) {
  await api.post("/recommendations/events", body);
}

export async function searchIssues(body: SearchRequest) {
  const { data } = await api.post<SearchResponse>("/search", body);
  return data;
}

export async function logSearchInteraction(body: SearchInteractionInput) {
  await api.post("/search/interact", body);
}

export async function fetchIssue(nodeId: string) {
  const { data } = await api.get<IssueDetailResponse>(`/issues/${encodeURIComponent(nodeId)}`);
  return data;
}

export async function fetchSimilarIssues(nodeId: string, limit = 5) {
  const { data } = await api.get<SimilarIssuesResponse>(`/issues/${encodeURIComponent(nodeId)}/similar`, {
    params: { limit },
  });
  return data;
}

export async function fetchRepositories(params: { q?: string; language?: string; limit?: number }) {
  const { data } = await api.get<RepositoriesResponse>("/repositories", { params });
  return data;
}

export async function fetchLanguages() {
  const { data } = await api.get<TaxonomyLanguagesResponse>("/taxonomy/languages");
  return data;
}

export async function fetchStackAreas() {
  const { data } = await api.get<TaxonomyStackAreasResponse>("/taxonomy/stack-areas");
  return data;
}

export async function authInit() {
  await api.get("/auth/init");
}

export async function fetchMe() {
  const { data } = await api.get<AuthMeResponse>("/auth/me");
  return data;
}

export async function listBookmarks(page = 1, pageSize = 20) {
  const { data } = await api.get<BookmarksListResponse>("/bookmarks", {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function createBookmark(input: {
  issue_node_id: string;
  github_url: string;
  title_snapshot: string;
  body_snapshot: string;
}) {
  const { data } = await api.post<Bookmark>("/bookmarks", input);
  return data;
}

export async function deleteBookmark(bookmarkId: string) {
  await api.delete(`/bookmarks/${encodeURIComponent(bookmarkId)}`);
}

export async function patchBookmark(bookmarkId: string, input: { is_resolved: boolean }) {
  const { data } = await api.patch<Bookmark>(`/bookmarks/${encodeURIComponent(bookmarkId)}`, input);
  return data;
}

export async function batchBookmarkCheck(issueNodeIds: string[]) {
  const { data } = await api.post<BookmarkBatchCheckResponse>("/bookmarks/check", {
    issue_node_ids: issueNodeIds,
  });
  return data;
}

export async function getBookmark(bookmarkId: string) {
  const { data } = await api.get<Bookmark>(`/bookmarks/${encodeURIComponent(bookmarkId)}`);
  return data;
}

export async function listNotes(bookmarkId: string) {
  const { data } = await api.get<NotesListResponse>(`/bookmarks/${encodeURIComponent(bookmarkId)}/notes`);
  return data;
}

export async function addNote(bookmarkId: string, content: string) {
  const { data } = await api.post(`/bookmarks/${encodeURIComponent(bookmarkId)}/notes`, { content });
  return data;
}

export async function updateNote(noteId: string, content: string) {
  const { data } = await api.patch(`/bookmarks/notes/${encodeURIComponent(noteId)}`, { content });
  return data;
}

export async function deleteNote(noteId: string) {
  const { data } = await api.delete(`/bookmarks/notes/${encodeURIComponent(noteId)}`);
  return data;
}

export async function fetchProfile() {
  const { data } = await api.get<ProfileResponse>("/profile");
  return data;
}

export async function fetchProfileOnboarding() {
  const { data } = await api.get<ProfileOnboardingResponse>("/profile/onboarding");
  return data;
}

export async function startOnboarding() {
  const { data } = await api.post<ProfileOnboardingResponse>("/profile/onboarding/start");
  return data;
}

export async function skipOnboarding() {
  const { data } = await api.post<ProfileOnboardingResponse>("/profile/onboarding/skip");
  return data;
}

export async function completeOnboarding() {
  const { data } = await api.post<ProfileOnboardingResponse>("/profile/onboarding/complete");
  return data;
}

export async function saveOnboardingStep(step: OnboardingStep, payload: unknown) {
  const { data } = await api.patch<OnboardingStepResponse>(`/profile/onboarding/step/${step}`, payload ?? {});
  return data;
}

export async function uploadResume(file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<ResumeUploadAcceptedResponse>("/profile/resume", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function fetchResumeData() {
  const { data } = await api.get<ResumeDataResponse>("/profile/resume");
  return data;
}

export async function initiateGithubFetch() {
  const { data } = await api.post<GitHubAcceptedResponse>("/profile/github");
  return data;
}

export async function fetchGithubData() {
  const { data } = await api.get<GitHubDataResponse>("/profile/github");
  return data;
}

export async function fetchPreferences() {
  const { data } = await api.get<ProfilePreferencesResponse>("/profile/preferences");
  return data;
}

export async function patchPreferences(payload: Partial<ProfilePreferences>) {
  const { data } = await api.patch<ProfilePreferencesResponse>("/profile/preferences", payload);
  return data;
}

export async function fetchLinkedAccounts() {
  const { data } = await api.get<LinkedAccountsResponse>("/auth/linked-accounts");
  return data;
}

export async function fetchSessions() {
  const { data } = await api.get<SessionsResponse>("/auth/sessions");
  return data;
}

export async function revokeSession(sessionId: string) {
  await api.delete(`/auth/sessions/${encodeURIComponent(sessionId)}`);
}

export async function revokeOtherSessions() {
  await api.delete("/auth/sessions");
}

export async function logout() {
  await api.post("/auth/logout");
}

export async function logoutAll() {
  await api.post("/auth/logout/all");
}

export async function deleteAccount() {
  await api.delete("/auth/account");
}

export async function unlinkAccount(provider: string) {
  const { data } = await api.delete<{ unlinked: boolean; provider: string }>(
    `/auth/link/${provider}`,
  );
  return data;
}
