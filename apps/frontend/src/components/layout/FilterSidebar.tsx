"use client";

import { ChevronDown, ChevronRight, SlidersHorizontal, X } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

export type FilterState = {
  language: string | null;
  label: string | null;
  repo: string | null;
};

type FilterSidebarProps = {
  isVisible: boolean;
  languages: string[];
  labels: string[];
  repos: string[];
  isLoadingLanguages?: boolean;
  isLoadingRepos?: boolean;
  value: FilterState;
  onChange: (next: FilterState) => void;
  onOpenRepoSection?: () => void;
};

export function FilterSidebar({
  isVisible,
  languages,
  labels,
  repos,
  isLoadingLanguages = false,
  isLoadingRepos = false,
  value,
  onChange,
  onOpenRepoSection,
}: FilterSidebarProps) {
  const hasActiveFilters = Boolean(value.language || value.label || value.repo);
  const [showAllLanguages, setShowAllLanguages] = useState(false);
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [showAllRepos, setShowAllRepos] = useState(false);
  const [repoSectionEnabled, setRepoSectionEnabled] = useState(false);

  const visibleLanguages = useMemo(() => (showAllLanguages ? languages : languages.slice(0, 8)), [showAllLanguages, languages]);
  const visibleLabels = useMemo(() => (showAllLabels ? labels : labels.slice(0, 8)), [showAllLabels, labels]);
  const visibleRepos = useMemo(() => (showAllRepos ? repos : repos.slice(0, 8)), [showAllRepos, repos]);

  if (!isVisible) {
    return null;
  }

  function clear() {
    onChange({ language: null, label: null, repo: null });
  }

  return (
    <aside
      className="h-full w-full overflow-y-auto pl-6 pr-4 pt-6"
      style={{ backgroundColor: "var(--sidebar)", borderRight: "1px solid var(--sidebar-border)" }}
    >
      <div className="space-y-6 pb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <SlidersHorizontal className="h-4 w-4" style={{ color: "rgba(255, 255, 255, 0.40)" }} />
            <h2 className="text-[16px] font-bold tracking-tight" style={{ color: "rgba(255, 255, 255, 0.90)" }}>
              Filters
            </h2>
          </div>
          {hasActiveFilters ? (
            <button
              type="button"
              onClick={clear}
              className="btn-press flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-medium transition-colors hover:bg-white/5"
              style={{ color: "rgba(255, 255, 255, 0.45)" }}
            >
              <X className="h-3 w-3" />
              Clear
            </button>
          ) : null}
        </div>

        <div className="h-px" style={{ backgroundColor: "rgba(255, 255, 255, 0.06)" }} />

        <FilterSection
          title="Language"
          items={visibleLanguages}
          selected={value.language}
          onSelect={(language) => onChange({ ...value, language })}
          canToggleMore={languages.length > visibleLanguages.length}
          expanded={showAllLanguages}
          onToggleExpanded={() => setShowAllLanguages((v) => !v)}
          moreCount={Math.max(0, languages.length - visibleLanguages.length)}
          isLoading={isLoadingLanguages}
        />

        <FilterSection
          title="Label"
          items={visibleLabels}
          selected={value.label}
          onSelect={(label) => onChange({ ...value, label })}
          canToggleMore={labels.length > visibleLabels.length}
          expanded={showAllLabels}
          onToggleExpanded={() => setShowAllLabels((v) => !v)}
          moreCount={Math.max(0, labels.length - visibleLabels.length)}
        />

        <FilterSection
          title="Repository"
          items={repoSectionEnabled ? visibleRepos : []}
          selected={value.repo}
          onSelect={(repo) => onChange({ ...value, repo })}
          canToggleMore={repoSectionEnabled && repos.length > visibleRepos.length}
          expanded={showAllRepos}
          onToggleExpanded={() => setShowAllRepos((v) => !v)}
          moreCount={repoSectionEnabled ? Math.max(0, repos.length - visibleRepos.length) : 0}
          truncate
          isLoading={repoSectionEnabled && isLoadingRepos}
          emptyMessage={repoSectionEnabled ? "No repositories available" : "Load repository filters on demand"}
          actionLabel={repoSectionEnabled ? undefined : "Load repositories"}
          onAction={
            repoSectionEnabled
              ? undefined
              : () => {
                  setRepoSectionEnabled(true);
                  onOpenRepoSection?.();
                }
          }
        />
      </div>
    </aside>
  );
}

function FilterSection(props: {
  title: string;
  items: string[];
  selected: string | null;
  onSelect: (value: string | null) => void;
  canToggleMore: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
  moreCount: number;
  truncate?: boolean;
  isLoading?: boolean;
  emptyMessage?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div>
      <label
        className="mb-2 block px-1 text-[10px] font-semibold uppercase tracking-widest"
        style={{ color: "#71717a", letterSpacing: "0.1em" }}
      >
        {props.title}
      </label>

      <div className="space-y-0.5">
        {props.onAction ? (
          <button
            type="button"
            onClick={props.onAction}
            className="btn-press flex w-full items-center gap-1.5 rounded-xl px-3 py-2 text-left text-[12px] transition-all duration-150 hover:bg-white/5"
            style={{ color: "rgba(255, 255, 255, 0.65)" }}
          >
            {props.actionLabel}
          </button>
        ) : null}

        {!props.onAction ? (
          <>
            <button
              type="button"
              onClick={() => props.onSelect(null)}
              className={cn(
                "btn-press relative w-full rounded-xl px-3 py-1.5 text-left text-[12px] transition-all duration-150 hover:bg-white/5 hover:text-[#E6E9F2]",
                props.truncate ? "truncate" : "",
              )}
              style={{
                backgroundColor: props.selected === null ? "rgba(138, 92, 255, 0.12)" : undefined,
                color: props.selected === null ? "#E6E9F2" : "#8A90B2",
                fontWeight: props.selected === null ? 600 : 400,
                borderLeft: props.selected === null ? "2px solid rgba(138, 92, 255, 0.6)" : "2px solid transparent",
              }}
            >
              All
            </button>

            {props.isLoading ? (
              <div
                className="rounded-xl px-3 py-2 text-[11px]"
                style={{ color: "rgba(255, 255, 255, 0.45)" }}
              >
                Loading…
              </div>
            ) : null}

            {props.items.map((item) => {
              const selected = props.selected === item;
              return (
                <button
                  key={item}
                  type="button"
                  onClick={() => props.onSelect(item)}
                  className={cn(
                    "btn-press relative w-full rounded-xl px-3 py-1.5 text-left text-[12px] transition-all duration-150 hover:bg-white/5 hover:text-[#E6E9F2]",
                    props.truncate ? "truncate" : "",
                  )}
                  style={{
                    backgroundColor: selected ? "rgba(138, 92, 255, 0.12)" : undefined,
                    color: selected ? "#E6E9F2" : "#8A90B2",
                    fontWeight: selected ? 600 : 400,
                    borderLeft: selected ? "2px solid rgba(138, 92, 255, 0.6)" : "2px solid transparent",
                  }}
                >
                  {item}
                </button>
              );
            })}

            {!props.isLoading && props.items.length === 0 ? (
              <div
                className="rounded-xl px-3 py-2 text-[11px]"
                style={{ color: "rgba(255, 255, 255, 0.35)" }}
              >
                {props.emptyMessage ?? "No options available"}
              </div>
            ) : null}
          </>
        ) : null}

        {!props.onAction && props.canToggleMore ? (
          <button
            type="button"
            onClick={props.onToggleExpanded}
            className="btn-press flex w-full items-center gap-1.5 rounded-xl px-3 py-1.5 text-left text-[11px] transition-all duration-150 hover:bg-white/5"
            style={{ color: "rgba(255, 255, 255, 0.45)" }}
          >
            {props.expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {props.expanded ? "Show less" : `Show ${props.moreCount} more`}
          </button>
        ) : null}
      </div>
    </div>
  );
}
