"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Menu, Search, Bookmark, User } from "lucide-react";
import { useState } from "react";
import type { Route } from "next";
import { setQueryParam } from "@/lib/url";
import { cn } from "@/lib/utils";

type TopNavProps = {
  activeTab: "browse" | "dashboard" | "for-you" | null;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  showSidebarToggle?: boolean;
};

export function TopNav({ activeTab, sidebarOpen, onToggleSidebar, showSidebarToggle = true }: TopNavProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [isFocused, setIsFocused] = useState(false);

  const q = searchParams.get("q") ?? "";

  function updateQuery(nextQ: string) {
    const url = new URL(pathname ?? "/", window.location.origin);
    url.search = searchParams.toString();
    setQueryParam(url, "q", nextQ);
    router.replace((url.pathname + url.search) as Route);
  }

  return (
    <nav
      className="fixed left-0 right-0 top-0 z-50"
      style={{
        height: "var(--topnav-height)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        background: "linear-gradient(180deg, rgba(22, 26, 43, 0.95), rgba(15, 18, 30, 0.95))",
        borderBottom: "1px solid rgba(138, 92, 255, 0.12)",
      }}
    >
      <div className="mx-auto flex h-full max-w-[1800px] items-center justify-between gap-6 px-6">
        <div className="flex items-center gap-6">
          {showSidebarToggle ? (
            <button
              type="button"
              onClick={onToggleSidebar}
              className={cn(
                "btn-press rounded-xl p-2 transition-all duration-200 hover:bg-white/5",
                sidebarOpen ? "opacity-100" : "opacity-90",
              )}
              title="Toggle filters"
            >
              <Menu className="h-5 w-5" style={{ color: "rgba(255, 255, 255, 0.6)" }} />
            </button>
          ) : null}

          <Link href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-xl"
              style={{
                background:
                  "linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(99, 102, 241, 0.1))",
              }}
            >
              <Search className="h-4 w-4" style={{ color: "#6366f1" }} />
            </div>
            <div className="text-[15px] tracking-tight">
              <span
                style={{ fontWeight: 800, color: "rgba(255, 255, 255, 0.95)", letterSpacing: "-0.02em" }}
              >
                ISSUE
              </span>
              <span
                style={{ fontWeight: 300, color: "rgba(255, 255, 255, 0.75)", letterSpacing: "-0.02em" }}
              >
                INDEX
              </span>
            </div>
          </Link>

          <div
            className="flex items-center rounded-xl p-1"
            style={{ backgroundColor: "#1A1A1A", border: "1px solid rgba(255, 255, 255, 0.05)" }}
          >
            <Link
              href="/browse"
              className="btn-press rounded-lg px-4 py-1.5 text-[13px] font-medium transition-all duration-200 hover:bg-white/10"
              style={{
                backgroundColor: activeTab === "browse" ? "rgba(99, 102, 241, 0.15)" : undefined,
                color: activeTab === "browse" ? "rgba(255, 255, 255, 0.95)" : "rgba(255, 255, 255, 0.55)",
              }}
            >
              Browse
            </Link>
            <Link
              href="/dashboard"
              className="btn-press rounded-lg px-4 py-1.5 text-[13px] font-medium transition-all duration-200 hover:bg-white/10"
              style={{
                backgroundColor: activeTab === "dashboard" ? "rgba(99, 102, 241, 0.15)" : undefined,
                color: activeTab === "dashboard" ? "rgba(255, 255, 255, 0.95)" : "rgba(255, 255, 255, 0.55)",
              }}
            >
              Trending
            </Link>
            <Link
              href="/for-you"
              className="btn-press rounded-lg px-4 py-1.5 text-[13px] font-medium transition-all duration-200 hover:bg-white/10"
              style={{
                backgroundColor: activeTab === "for-you" ? "rgba(99, 102, 241, 0.15)" : undefined,
                color: activeTab === "for-you" ? "rgba(255, 255, 255, 0.95)" : "rgba(255, 255, 255, 0.55)",
              }}
            >
              For You
            </Link>
          </div>
        </div>

        <div className="flex-1" />

        <div className="flex w-full max-w-2xl flex-1 items-center justify-center">
          <div className="relative w-full">
            {isFocused ? (
              <div
                className="absolute -inset-0.5 rounded-xl"
                style={{
                  background: "linear-gradient(135deg, rgba(138, 92, 255, 0.3), rgba(99, 102, 241, 0.2))",
                  filter: "blur(12px)",
                }}
              />
            ) : null}
            <div
              className="relative flex items-center gap-3 overflow-hidden rounded-xl px-4 py-2"
              style={{
                backgroundColor: "rgba(24, 24, 27, 0.6)",
                border: `1px solid ${isFocused ? "rgba(138, 92, 255, 0.4)" : "rgba(255, 255, 255, 0.08)"}`,
              }}
            >
              <Search
                className="h-4 w-4 flex-shrink-0"
                style={{ color: isFocused ? "rgba(138, 92, 255, 0.95)" : "rgba(255, 255, 255, 0.40)" }}
              />
              <input
                value={q}
                onChange={(e) => updateQuery(e.target.value)}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                placeholder="Search issues..."
                className="flex-1 bg-transparent text-[14px] font-medium outline-none placeholder:text-white/30"
                style={{ color: "#E6E9F2", letterSpacing: "-0.01em" }}
              />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/saved"
            className="btn-press btn-glow rounded-xl p-2 transition-all duration-200 hover:bg-white/5"
            title="Saved issues"
          >
            <Bookmark className="h-5 w-5" style={{ color: "rgba(255, 255, 255, 0.6)" }} />
          </Link>

          <Link
            href="/profile"
            className="btn-press btn-glow rounded-xl border px-3 py-2 transition-all duration-200 hover:bg-white/5"
            style={{ borderColor: "rgba(255,255,255,0.05)" }}
            title="Profile"
          >
            <div className="flex items-center gap-2">
              <div
                className="flex h-6 w-6 items-center justify-center rounded-full"
                style={{ backgroundColor: "#18181b", border: "1px solid rgba(255, 255, 255, 0.1)" }}
              >
                <User className="h-3.5 w-3.5" style={{ color: "rgba(255, 255, 255, 0.7)" }} />
              </div>
            </div>
          </Link>
        </div>
      </div>
    </nav>
  );
}
