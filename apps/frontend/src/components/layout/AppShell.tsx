"use client";

import { PropsWithChildren, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { useQuery } from "@tanstack/react-query";
import { fetchLanguages, fetchRepositories } from "@/lib/api/endpoints";
import { setQueryParam } from "@/lib/url";
import { cn } from "@/lib/utils";
import { TopNav } from "./TopNav";
import { FilterSidebar, type FilterState } from "./FilterSidebar";

const DEFAULT_LABELS = [
  "bug",
  "good first issue",
  "help wanted",
  "enhancement",
  "documentation",
  "performance",
  "security",
];

export function AppShell({
  activeTab,
  children,
}: PropsWithChildren<{ activeTab: "browse" | "dashboard" | "for-you" | null }>) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [filterDataEnabled, setFilterDataEnabled] = useState(false);
  const [repoDataEnabled, setRepoDataEnabled] = useState(false);

  const filterState: FilterState = useMemo(
    () => ({
      language: searchParams.get("lang") ?? null,
      label: searchParams.get("label") ?? null,
      repo: searchParams.get("repo") ?? null,
    }),
    [searchParams],
  );

  function updateFilters(next: FilterState) {
    const url = new URL(pathname ?? "/", window.location.origin);
    url.search = searchParams.toString();

    setQueryParam(url, "lang", next.language);
    setQueryParam(url, "label", next.label);
    setQueryParam(url, "repo", next.repo);

    router.replace((url.pathname + url.search) as Route);
  }

  function toggleSidebar() {
    setSidebarOpen((current) => {
      const next = !current;
      if (next) {
        setFilterDataEnabled(true);
      }
      return next;
    });
  }

  const languagesQuery = useQuery({
    queryKey: ["taxonomy", "languages"],
    queryFn: fetchLanguages,
    staleTime: 1000 * 60 * 30,
    enabled: filterDataEnabled,
  });

  const reposQuery = useQuery({
    queryKey: ["repositories", "sidebar", filterState.language ?? "", ""],
    queryFn: () =>
      fetchRepositories({
        language: filterState.language ?? undefined,
        q: "",
        limit: 25,
      }),
    staleTime: 1000 * 60 * 10,
    enabled: repoDataEnabled,
  });

  const languages = useMemo(() => languagesQuery.data?.languages ?? [], [languagesQuery.data]);
  const repos = useMemo(() => reposQuery.data?.repositories.map((r) => r.name) ?? [], [reposQuery.data]);

  return (
    <div className="min-h-screen bg-background">
      <TopNav activeTab={activeTab} sidebarOpen={sidebarOpen} onToggleSidebar={toggleSidebar} />

      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50 transition-opacity duration-300 md:hidden",
          sidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={() => setSidebarOpen(false)}
      />

      <div
        className={cn(
          "fixed bottom-0 left-0 top-[var(--topnav-height)] z-40 w-[var(--sidebar-width)] transition-transform duration-300",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <FilterSidebar
          isVisible={true}
          languages={languages}
          labels={DEFAULT_LABELS}
          repos={repos}
          isLoadingLanguages={languagesQuery.isLoading}
          isLoadingRepos={reposQuery.isLoading}
          value={filterState}
          onChange={updateFilters}
          onOpenRepoSection={() => setRepoDataEnabled(true)}
        />
      </div>

      <main
        className={cn(
          "min-h-screen pt-[var(--topnav-height)] transition-[margin-left] duration-300",
          sidebarOpen ? "md:ml-[var(--sidebar-width)]" : "md:ml-0"
        )}
      >
        <div className="px-4 py-6 md:px-8 md:py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
