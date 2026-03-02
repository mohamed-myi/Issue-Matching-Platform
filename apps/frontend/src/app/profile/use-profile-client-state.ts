"use client";

import { useCallback, useState } from "react";

export type TabId =
  | "overview"
  | "onboarding"
  | "intent"
  | "preferences"
  | "accounts"
  | "danger";

export function toTabId(value: string): TabId {
  const allowed: TabId[] = ["overview", "onboarding", "intent", "preferences", "accounts", "danger"];
  return (allowed.includes(value as TabId) ? value : "overview") as TabId;
}

export function useProfileTabState(
  initialTab: string,
  onNavigate: (tab: TabId) => void,
) {
  const [tab, setTab] = useState<TabId>(() => toTabId(initialTab));

  const goToTab = useCallback(
    (next: TabId) => {
      setTab(next);
      onNavigate(next);
    },
    [onNavigate],
  );

  return {
    tab,
    goToTab,
  };
}
