"use client";

import type { Route } from "next";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  CircleDot,
  FileText,
  Github,
  Loader2,
  MessageSquareText,
  Sparkles,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState } from "@/components/common/EmptyState";
import { useToast } from "@/components/common/Toast";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  AccountCard,
  ActionButton,
  formatStatus,
  InputCard,
  Section,
  SourceCard,
  StatCard,
  StatusBadge,
  statusColor,
  TabButton,
} from "./profile-client-components";
import {
  type TabId,
  useProfileTabState,
} from "./use-profile-client-state";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { getApiErrorMessage } from "@/lib/api/client";
import {
  useCompleteOnboarding,
  useDeleteAccount,
  useInitiateGithubFetch,
  useLinkedAccounts,
  useLogout,
  useLogoutAll,
  useMe,
  useOnboarding,
  usePatchPreferences,
  usePreferences,
  useProfile,
  useSaveOnboardingStep,
  useSkipOnboarding,
  useStartOnboarding,
  useUnlinkAccount,
  useUploadResume,
} from "@/lib/api/hooks";
import { getOAuthErrorMessage } from "@/lib/auth/oauth-error-messages";
import { useAuthGuard } from "@/lib/hooks/use-auth-guard";

export default function ProfileClient(props: {
  initialTab: string;
  connected: string | null;
  initialError: string | null;
}) {
  const router = useRouter();
  const { showToast, ToastContainer } = useToast();
  const { tab, goToTab } = useProfileTabState(props.initialTab, (next) => {
    router.replace(`/profile?tab=${next}` as Route);
  });
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [unlinkDialogOpen, setUnlinkDialogOpen] = useState(false);
  const [unlinkProvider, setUnlinkProvider] = useState<string | null>(null);
  const [intentLanguages, setIntentLanguages] = useState("");
  const [intentStackAreas, setIntentStackAreas] = useState("");
  const [intentText, setIntentText] = useState("");
  const [intentExperience, setIntentExperience] = useState("");
  const resumeInputRef = useRef<HTMLInputElement>(null);
  const hasAutoFetchedGithub = useRef(false);
  const hasInitializedIntent = useRef(false);

  const { isRedirecting } = useAuthGuard();
  const meQuery = useMe();
  const profileQuery = useProfile({
    refetchInterval: (query) => (query.state.data?.is_calculating ? 3000 : false),
  });
  const onboardingQuery = useOnboarding({
    refetchInterval: () => (profileQuery.data?.is_calculating ? 3000 : false),
  });
  const preferencesQuery = usePreferences();
  const accountsQuery = useLinkedAccounts();

  useEffect(() => {
    if (props.initialError) {
      showToast(getOAuthErrorMessage(props.initialError), "error");
    }
    if (props.connected === "github") {
      showToast("GitHub connected successfully.", "success");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);



  const startOnboardingMutation = useStartOnboarding({
    onSuccess: () => {
      showToast("Onboarding started.", "success");
      goToTab("onboarding");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const skipOnboardingMutation = useSkipOnboarding({
    onSuccess: () => {
      showToast("Onboarding skipped. You can restart it anytime.", "info");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const completeOnboardingMutation = useCompleteOnboarding({
    onSuccess: () => {
      showToast("Onboarding completed! Your personalized feed is ready.", "success");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const saveIntentMutation = useSaveOnboardingStep({
    onSuccess: () => {
      showToast("Intent profile saved.", "success");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const uploadResumeMutation = useUploadResume({
    onSuccess: () => {
      showToast("Resume uploaded. Processing started.", "success");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const fetchGithubMutation = useInitiateGithubFetch({
    onSuccess: () => {
      showToast("GitHub sync started.", "success");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });
  const triggerGithubFetch = fetchGithubMutation.mutate;
  const isGithubFetchPending = fetchGithubMutation.isPending;

  const patchPreferencesMutation = usePatchPreferences({
    onSuccess: () => {
      showToast("Preferences updated.", "success");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const logoutMutation = useLogout({
    onSuccess: () => {
      router.replace("/login");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const logoutAllMutation = useLogoutAll({
    onSuccess: () => {
      router.replace("/login");
    },
    onError: (e) => showToast(getApiErrorMessage(e), "error"),
  });

  const deleteAccountMutation = useDeleteAccount({
    onSuccess: () => {
      router.replace("/");
    },
    onError: (e) => {
      setDeleteDialogOpen(false);
      showToast(getApiErrorMessage(e), "error");
    },
  });

  const unlinkAccountMutation = useUnlinkAccount({
    onSuccess: () => {
      showToast("Account unlinked successfully.", "success");
      setUnlinkDialogOpen(false);
      setUnlinkProvider(null);
    },
    onError: (e) => {
      setUnlinkDialogOpen(false);
      setUnlinkProvider(null);
      showToast(getApiErrorMessage(e), "error");
    },
  });



  const isAuthed = meQuery.isSuccess;

  const base = getApiBaseUrl();
  const linkGithubUrl = `${base}/auth/link/github`;
  const linkGoogleUrl = `${base}/auth/link/google`;
  const connectGithubUrl = `${base}/auth/connect/github`;

  const overview = useMemo(() => {
    const p = profileQuery.data;
    if (!p) return null;
    return {
      optimization: p.optimization_percent,
      onboarding: p.onboarding_status,
      calculating: p.is_calculating,
    };
  }, [profileQuery.data]);


  const createdVia = meQuery.data?.created_via ?? null;
  const hasGithubLogin = !!meQuery.data?.github_username;
  const hasGoogleLogin = !!meQuery.data?.google_id;
  const githubConnected = !!accountsQuery.data?.accounts?.some(
    (account) => account.provider === "github" && account.connected,
  );

  useEffect(() => {
    const intent = profileQuery.data?.sources?.intent?.data as
      | { languages?: string[]; stack_areas?: string[]; text?: string; experience_level?: string | null }
      | undefined;
    if (!intent || hasInitializedIntent.current) return;
    setIntentLanguages((intent.languages ?? []).join(", "));
    setIntentStackAreas((intent.stack_areas ?? []).join(", "));
    setIntentText(intent.text ?? "");
    setIntentExperience(intent.experience_level ?? "");
    hasInitializedIntent.current = true;
  }, [profileQuery.data?.sources?.intent?.data]);

  useEffect(() => {
    if (
      props.connected === "github" &&
      githubConnected &&
      !onboardingQuery.data?.completed_steps.includes("github") &&
      !isGithubFetchPending &&
      !hasAutoFetchedGithub.current
    ) {
      hasAutoFetchedGithub.current = true;
      triggerGithubFetch();
    }
  }, [
    props.connected,
    githubConnected,
    onboardingQuery.data?.completed_steps,
    isGithubFetchPending,
    triggerGithubFetch,
  ]);

  if (isRedirecting) return null;



  return (
    <AppShell activeTab={null}>
      <div className="mb-6">
        <div
          className="text-xs font-semibold uppercase tracking-widest"
          style={{ color: "#71717a" }}
        >
          Profile
        </div>
        <h1 className="mt-2 text-xl font-semibold tracking-tight">Your account</h1>
        <div className="mt-2 text-sm" style={{ color: "rgba(138,144,178,1)" }}>
          {isAuthed ? `Signed in as ${meQuery.data.email}` : "Not signed in"}
        </div>
      </div>

      {!isAuthed ? (
        <EmptyState
          title="Sign in required"
          description={
            getApiErrorMessage(meQuery.error) + " — go to Login to continue."
          }
        />
      ) : (
        <>
          <ToastContainer />

          <div className="mb-6 flex flex-wrap gap-2">
            {(
              [
                ["overview", "Overview"],
                ["onboarding", "Onboarding"],
                ["intent", "Intent"],
                ["preferences", "Preferences"],
                ["accounts", "Accounts"],
                ["danger", "Account Deletion"],
              ] as [TabId, string][]
            ).map(([id, label]) => (
              <TabButton key={id} active={tab === id} onClick={() => goToTab(id)}>
                {label}
              </TabButton>
            ))}
          </div>

          {tab === "overview" && (
            <Section title="Overview">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <StatCard
                  label="Optimization"
                  value={overview ? `${overview.optimization}%` : "—"}
                  description="Profile completeness score. Intent contributes 50%, resume 30%, and GitHub 20%."
                />
                <StatCard
                  label="Onboarding"
                  value={overview ? formatStatus(overview.onboarding) : "—"}
                  description="Your onboarding status. Complete onboarding to unlock personalized recommendations."
                  statusColor={statusColor(overview?.onboarding ?? null)}
                />
                <StatCard
                  label="Calculating"
                  value={
                    overview
                      ? overview.calculating
                        ? "In progress"
                        : "Idle"
                      : "—"
                  }
                  description="Whether the system is currently computing your recommendation vectors."
                />
              </div>

              <div
                className="mt-6 pt-6"
                style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}
              >
                <div className="text-sm font-semibold mb-1">Session</div>
                <div
                  className="mb-3 text-xs"
                  style={{ color: "rgba(138,144,178,1)" }}
                >
                  Manage your active sessions across devices.
                </div>
                <div className="flex flex-wrap gap-2">
                  <ActionButton
                    onClick={() => logoutMutation.mutate()}
                    disabled={logoutMutation.isPending}
                  >
                    {logoutMutation.isPending ? "Logging out..." : "Log out"}
                  </ActionButton>
                  <ActionButton
                    onClick={() => logoutAllMutation.mutate()}
                    disabled={logoutAllMutation.isPending}
                  >
                    {logoutAllMutation.isPending
                      ? "Logging out..."
                      : "Log out on all devices"}
                  </ActionButton>
                </div>
              </div>
            </Section>
          )}

          {tab === "onboarding" && (
            <div className="space-y-4">
              <Section title="Personalize Your Feed">
                <div
                  className="rounded-xl p-4 mb-4"
                  style={{
                    background:
                      "linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(138, 92, 255, 0.04))",
                    border: "1px solid rgba(99, 102, 241, 0.15)",
                  }}
                >
                  <div className="flex items-start gap-3">
                    <Sparkles
                      className="mt-0.5 h-5 w-5 flex-shrink-0"
                      style={{ color: "rgba(138, 92, 255, 0.95)" }}
                    />
                    <div>
                      <div
                        className="text-sm font-semibold"
                        style={{ color: "rgba(230,233,242,0.95)" }}
                      >
                        Build your developer profile to get personalized issue
                        recommendations
                      </div>
                      <div
                        className="mt-1 text-xs leading-relaxed"
                        style={{ color: "rgba(138,144,178,1)" }}
                      >
                        Add at least one source below to unlock your personalized
                        feed. Each source generates a vector that powers
                        recommendations matched to your skills and interests.
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xs font-medium" style={{ color: "rgba(138,144,178,1)" }}>
                    Status:
                  </span>
                  <StatusBadge status={onboardingQuery.data?.status ?? "not_started"} />
                  {profileQuery.data?.is_calculating ? (
                    <span className="inline-flex items-center gap-1 text-xs" style={{ color: "rgba(138,144,178,1)" }}>
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Processing profile sources
                    </span>
                  ) : null}
                </div>

                {onboardingQuery.data && (
                  <div className="mb-4 space-y-1.5">
                    {[
                      { id: "welcome", label: "Welcome" },
                      { id: "intent", label: "Intent profile" },
                      { id: "github", label: "GitHub connected" },
                      { id: "resume", label: "Resume uploaded" },
                      { id: "preferences", label: "Preferences set" },
                    ].map((step) => {
                      const done =
                        onboardingQuery.data.completed_steps.includes(step.id);
                      return (
                        <div
                          key={step.id}
                          className="flex items-center gap-2 text-xs"
                        >
                          {done ? (
                            <Check
                              className="h-3.5 w-3.5"
                              style={{ color: "rgba(34, 197, 94, 1)" }}
                            />
                          ) : (
                            <CircleDot
                              className="h-3.5 w-3.5"
                              style={{ color: "rgba(113,113,122,0.6)" }}
                            />
                          )}
                          <span
                            style={{
                              color: done
                                ? "rgba(230,233,242,0.95)"
                                : "rgba(138,144,178,0.8)",
                            }}
                          >
                            {step.label}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Section>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <SourceCard
                  icon={<MessageSquareText className="h-5 w-5" />}
                  title="Intent"
                  weight="50%"
                  description="Tell us your preferred languages, stack areas, and what kind of projects interest you."
                  completed={onboardingQuery.data?.completed_steps.includes("intent") ?? false}
                  actionLabel="Set intent"
                  onAction={() => goToTab("intent")}
                />
                <SourceCard
                  icon={<FileText className="h-5 w-5" />}
                  title="Resume"
                  weight="30%"
                  description="Upload your resume to automatically extract skills and job titles via AI parsing."
                  completed={onboardingQuery.data?.completed_steps.includes("resume") ?? false}
                  actionLabel={uploadResumeMutation.isPending ? "Uploading..." : "Upload resume"}
                  onAction={() => resumeInputRef.current?.click()}
                  disabled={uploadResumeMutation.isPending}
                  note="PDF or DOCX, max 5 MB"
                />
                <SourceCard
                  icon={<Github className="h-5 w-5" />}
                  title="GitHub"
                  weight="20%"
                  description="Connect your GitHub to analyze starred repos and contributions for skill signals."
                  completed={onboardingQuery.data?.completed_steps.includes("github") ?? false}
                  actionLabel={
                    githubConnected
                      ? fetchGithubMutation.isPending
                        ? "Syncing..."
                        : "Sync GitHub data"
                      : "Connect GitHub"
                  }
                  href={githubConnected ? undefined : connectGithubUrl}
                  onAction={githubConnected ? () => fetchGithubMutation.mutate() : undefined}
                  disabled={fetchGithubMutation.isPending}
                />
              </div>
              <input
                ref={resumeInputRef}
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    uploadResumeMutation.mutate(file);
                  }
                  e.currentTarget.value = "";
                }}
              />

              <Section title="Finalize">
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      if (onboardingQuery.data?.status === "not_started") {
                        startOnboardingMutation.mutate();
                      }
                      completeOnboardingMutation.mutate();
                    }}
                    disabled={
                      completeOnboardingMutation.isPending ||
                      !onboardingQuery.data?.can_complete
                    }
                    className="btn-press btn-glow rounded-xl px-5 py-2.5 text-sm font-semibold transition-colors disabled:opacity-40 hover:brightness-110"
                    style={{
                      backgroundColor: onboardingQuery.data?.can_complete
                        ? "rgba(99, 102, 241, 0.7)"
                        : "rgba(99, 102, 241, 0.15)",
                      border: "1px solid rgba(99, 102, 241, 0.5)",
                      color: "rgba(255,255,255,0.95)",
                    }}
                  >
                    {completeOnboardingMutation.isPending ? (
                      <span className="flex items-center gap-2">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Completing...
                      </span>
                    ) : (
                      "Complete Onboarding"
                    )}
                  </button>

                  {!onboardingQuery.data?.can_complete && (
                    <span
                      className="text-xs"
                      style={{ color: "rgba(138,144,178,0.7)" }}
                    >
                      Add at least one source (intent, resume, or GitHub) to
                      enable completion.
                    </span>
                  )}
                </div>

                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => skipOnboardingMutation.mutate()}
                    disabled={skipOnboardingMutation.isPending}
                    className="btn-press text-xs font-medium transition-colors hover:underline"
                    style={{ color: "rgba(138,144,178,0.8)" }}
                  >
                    {skipOnboardingMutation.isPending
                      ? "Skipping..."
                      : "Skip for now"}
                  </button>
                </div>
              </Section>
            </div>
          )}

          {tab === "intent" && (
            <Section title="Intent Profile">
              <div className="text-sm" style={{ color: "rgba(138,144,178,1)" }}>
                This source has the strongest personalization weight. Add your target stack and goals.
              </div>

              <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div
                  className="rounded-2xl border p-4"
                  style={{
                    borderColor: "rgba(255,255,255,0.08)",
                    backgroundColor: "rgba(24, 24, 27, 0.25)",
                  }}
                >
                  <div
                    className="text-xs font-semibold"
                    style={{ color: "rgba(230,233,242,0.95)" }}
                  >
                    Languages
                  </div>
                  <div
                    className="mt-1 text-[11px] leading-relaxed"
                    style={{ color: "rgba(138,144,178,0.7)" }}
                  >
                    Comma-separated list (at least one).
                  </div>
                  <input
                    value={intentLanguages}
                    onChange={(e) => setIntentLanguages(e.target.value)}
                    placeholder="e.g. TypeScript, Python"
                    className="mt-3 w-full rounded-xl border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-white/20 focus:ring-1 focus:ring-[rgba(138,92,255,0.4)] focus:border-[rgba(138,92,255,0.4)]"
                    style={{
                      borderColor: "rgba(255,255,255,0.10)",
                      color: "rgba(230,233,242,0.95)",
                    }}
                  />
                </div>
                <div
                  className="rounded-2xl border p-4"
                  style={{
                    borderColor: "rgba(255,255,255,0.08)",
                    backgroundColor: "rgba(24, 24, 27, 0.25)",
                  }}
                >
                  <div
                    className="text-xs font-semibold"
                    style={{ color: "rgba(230,233,242,0.95)" }}
                  >
                    Stack Areas
                  </div>
                  <div
                    className="mt-1 text-[11px] leading-relaxed"
                    style={{ color: "rgba(138,144,178,0.7)" }}
                  >
                    Comma-separated areas (at least one).
                  </div>
                  <input
                    value={intentStackAreas}
                    onChange={(e) => setIntentStackAreas(e.target.value)}
                    placeholder="e.g. frontend, backend, infra"
                    className="mt-3 w-full rounded-xl border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-white/20 focus:ring-1 focus:ring-[rgba(138,92,255,0.4)] focus:border-[rgba(138,92,255,0.4)]"
                    style={{
                      borderColor: "rgba(255,255,255,0.10)",
                      color: "rgba(230,233,242,0.95)",
                    }}
                  />
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-4">
                <div
                  className="rounded-2xl border p-4"
                  style={{
                    borderColor: "rgba(255,255,255,0.08)",
                    backgroundColor: "rgba(24, 24, 27, 0.25)",
                  }}
                >
                  <div
                    className="text-xs font-semibold"
                    style={{ color: "rgba(230,233,242,0.95)" }}
                  >
                    Intent Text
                  </div>
                  <div
                    className="mt-1 text-[11px] leading-relaxed"
                    style={{ color: "rgba(138,144,178,0.7)" }}
                  >
                    Describe projects you want to work on (minimum 10 characters).
                  </div>
                  <textarea
                    value={intentText}
                    onChange={(e) => setIntentText(e.target.value)}
                    placeholder="I want to contribute to developer tooling, performance, and TypeScript-heavy repositories."
                    className="mt-3 min-h-[110px] w-full resize-y rounded-xl border bg-transparent p-3 text-sm outline-none placeholder:text-white/20 focus:ring-1 focus:ring-[rgba(138,92,255,0.4)] focus:border-[rgba(138,92,255,0.4)]"
                    style={{
                      borderColor: "rgba(255,255,255,0.10)",
                      color: "rgba(230,233,242,0.95)",
                    }}
                  />
                </div>
                <div
                  className="rounded-2xl border p-4"
                  style={{
                    borderColor: "rgba(255,255,255,0.08)",
                    backgroundColor: "rgba(24, 24, 27, 0.25)",
                  }}
                >
                  <div
                    className="text-xs font-semibold"
                    style={{ color: "rgba(230,233,242,0.95)" }}
                  >
                    Experience Level (optional)
                  </div>
                  <input
                    value={intentExperience}
                    onChange={(e) => setIntentExperience(e.target.value)}
                    placeholder="junior / mid / senior"
                    className="mt-3 w-full rounded-xl border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-white/20 focus:ring-1 focus:ring-[rgba(138,92,255,0.4)] focus:border-[rgba(138,92,255,0.4)]"
                    style={{
                      borderColor: "rgba(255,255,255,0.10)",
                      color: "rgba(230,233,242,0.95)",
                    }}
                  />
                </div>
              </div>

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => {
                    const languages = intentLanguages
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean);
                    const stackAreas = intentStackAreas
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean);
                    if (languages.length === 0 || stackAreas.length === 0 || intentText.trim().length < 10) {
                      showToast("Please provide languages, stack areas, and at least 10 characters of intent text.", "error");
                      return;
                    }
                    saveIntentMutation.mutate({
                      step: "intent",
                      payload: {
                        languages,
                        stack_areas: stackAreas,
                        text: intentText.trim(),
                        experience_level: intentExperience.trim() ? intentExperience.trim() : null,
                      },
                    });
                  }}
                  disabled={saveIntentMutation.isPending}
                  className="btn-press btn-glow rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 transition-colors hover:bg-white/5"
                  style={{
                    backgroundColor: "rgba(99, 102, 241, 0.15)",
                    border: "1px solid rgba(99, 102, 241, 0.35)",
                  }}
                >
                  {saveIntentMutation.isPending ? "Saving..." : "Save intent"}
                </button>
              </div>
            </Section>
          )}

          {tab === "preferences" && (
            <Section title="Preferences">
              <div className="text-sm" style={{ color: "rgba(138,144,178,1)" }}>
                These preferences control how your feed is filtered. They work
                alongside your profile vectors for more precise recommendations.
              </div>

              <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                <InputCard
                  key={`languages-${preferencesQuery.dataUpdatedAt}`}
                  label="Preferred languages"
                  description="Programming languages to prioritize in your feed. Used as an exact-match filter in the first retrieval stage."
                  placeholder="e.g. Python, TypeScript, Rust"
                  value={(preferencesQuery.data?.preferred_languages ?? []).join(
                    ", ",
                  )}
                  isSaving={patchPreferencesMutation.isPending}
                  onSave={(value) =>
                    patchPreferencesMutation.mutate({
                      preferred_languages: value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
                <InputCard
                  key={`topics-${preferencesQuery.dataUpdatedAt}`}
                  label="Preferred topics"
                  description="Topic areas to boost in recommendations. These expand your results beyond exact language matches."
                  placeholder="e.g. machine-learning, web, cli"
                  value={(preferencesQuery.data?.preferred_topics ?? []).join(
                    ", ",
                  )}
                  isSaving={patchPreferencesMutation.isPending}
                  onSave={(value) =>
                    patchPreferencesMutation.mutate({
                      preferred_topics: value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
                <InputCard
                  key={`heat-${preferencesQuery.dataUpdatedAt}`}
                  label="Min heat threshold"
                  description="Quality floor for recommendations. 0.0 shows all issues, 1.0 only the most active. Default is 0.6."
                  placeholder="0.6"
                  value={String(
                    preferencesQuery.data?.min_heat_threshold ?? 0.6,
                  )}
                  isSaving={patchPreferencesMutation.isPending}
                  onSave={(value) =>
                    patchPreferencesMutation.mutate({
                      min_heat_threshold: Number(value),
                    })
                  }
                />
              </div>
            </Section>
          )}

          {tab === "accounts" && (
            <Section title="Linked accounts">
              <div
                className="text-sm mb-4"
                style={{ color: "rgba(138,144,178,1)" }}
              >
                Link additional login methods to your account. You can sign in
                with any linked provider.
              </div>

              <div className="mb-5 flex flex-wrap gap-2">
                {!hasGithubLogin && (
                  <a
                    className="btn-press rounded-xl border px-4 py-2 text-sm font-medium transition-colors hover:bg-white/5"
                    style={{ borderColor: "rgba(255,255,255,0.10)" }}
                    href={linkGithubUrl}
                  >
                    Link GitHub login
                  </a>
                )}
                {!hasGoogleLogin && (
                  <a
                    className="btn-press rounded-xl border px-4 py-2 text-sm font-medium transition-colors hover:bg-white/5"
                    style={{ borderColor: "rgba(255,255,255,0.10)" }}
                    href={linkGoogleUrl}
                  >
                    Link Google login
                  </a>
                )}
                {hasGithubLogin && hasGoogleLogin && (
                  <div
                    className="text-xs"
                    style={{ color: "rgba(138,144,178,0.7)" }}
                  >
                    All available providers are linked.
                  </div>
                )}
              </div>

              {accountsQuery.isError ? (
                <EmptyState
                  title="Unable to load linked accounts"
                  description={getApiErrorMessage(accountsQuery.error)}
                />
              ) : (
                <div className="space-y-3">
                  <AccountCard
                    provider="github"
                    providerLabel="GitHub"
                    connected={hasGithubLogin}
                    username={meQuery.data?.github_username ?? null}
                    isPrimary={createdVia === "github"}
                    onUnlink={() => {
                      setUnlinkProvider("github");
                      setUnlinkDialogOpen(true);
                    }}
                  />
                  <AccountCard
                    provider="google"
                    providerLabel="Google"
                    connected={hasGoogleLogin}
                    username={meQuery.data?.email ?? null}
                    isPrimary={createdVia === "google"}
                    onUnlink={() => {
                      setUnlinkProvider("google");
                      setUnlinkDialogOpen(true);
                    }}
                  />
                </div>
              )}

              <ConfirmDialog
                open={unlinkDialogOpen}
                onOpenChange={setUnlinkDialogOpen}
                title={`Unlink ${unlinkProvider ?? "provider"}?`}
                description={`You will no longer be able to sign in with ${unlinkProvider ?? "this provider"}. You can re-link it later from this page.`}
                confirmLabel="Unlink"
                variant="danger"
                isPending={unlinkAccountMutation.isPending}
                onConfirm={() => {
                  if (unlinkProvider) unlinkAccountMutation.mutate(unlinkProvider);
                }}
              />
            </Section>
          )}

          {tab === "danger" && (
            <Section title="Danger Zone">
              <div className="text-sm" style={{ color: "rgba(138,144,178,1)" }}>
                This permanently deletes your account and all associated data.
                This action is irreversible and compliant with GDPR data
                deletion requirements.
              </div>

              <div className="mt-4 text-sm" style={{ color: "rgba(138,144,178,1)" }}>
                The following will be permanently deleted:
              </div>
              <ul
                className="mt-2 space-y-1 text-sm list-disc list-inside"
                style={{ color: "rgba(138,144,178,0.8)" }}
              >
                <li>Your user profile and all profile vectors</li>
                <li>Intent, resume, and GitHub profile data</li>
                <li>Feed preferences and recommendation history</li>
                <li>All linked OAuth accounts and tokens</li>
                <li>Saved bookmarks and notes</li>
                <li>All active sessions</li>
              </ul>

              <div className="mt-6 flex justify-end">
                <button
                  type="button"
                  className="btn-press rounded-xl border px-5 py-2.5 text-sm font-semibold transition-colors hover:brightness-110"
                  style={{
                    backgroundColor: "transparent",
                    borderColor: "rgba(220, 38, 38, 0.3)",
                    color: "rgba(248, 113, 113, 1)",
                  }}
                  onClick={() => setDeleteDialogOpen(true)}
                  disabled={deleteAccountMutation.isPending}
                >
                  {deleteAccountMutation.isPending ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Deleting...
                    </span>
                  ) : (
                    "Delete account"
                  )}
                </button>
              </div>

              <ConfirmDialog
                open={deleteDialogOpen}
                onOpenChange={setDeleteDialogOpen}
                title="Delete your account?"
                description="This will permanently delete your account and all associated data. This cannot be undone."
                confirmLabel="Delete my account"
                variant="danger"
                requiredConfirmText="DELETE"
                isPending={deleteAccountMutation.isPending}
                onConfirm={() => deleteAccountMutation.mutate()}
              />
            </Section>
          )}
        </>
      )}
    </AppShell>
  );
}
