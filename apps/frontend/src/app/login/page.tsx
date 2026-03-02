"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { authInit } from "@/lib/api/endpoints";
import { getApiErrorMessage } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { useMe } from "@/lib/api/hooks";
import { getOAuthErrorMessage } from "@/lib/auth/oauth-error-messages";
import type { OAuthProvider } from "@/lib/api/types";

export default function LoginPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const meQuery = useMe();

  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState<OAuthProvider | null>(null);
  const oauthError = useMemo(() => {
    const errorCode = searchParams.get("error");
    if (!errorCode) return null;
    const provider = searchParams.get("provider");
    return getOAuthErrorMessage(errorCode, provider);
  }, [searchParams]);

  useEffect(() => {
    if (meQuery.isSuccess) {
      router.replace("/dashboard");
    }
  }, [meQuery.isSuccess, router]);

  useEffect(() => {
    if (oauthError) {
      router.replace("/login");
    }
  }, [oauthError, router]);

  async function startLogin(provider: OAuthProvider) {
    setError(null);
    setIsStarting(provider);
    try {
      await authInit();

      const base = getApiBaseUrl();
      const url = new URL(`${base}/auth/login/${provider}`, window.location.origin);
      url.searchParams.set("remember_me", rememberMe ? "true" : "false");

      window.location.href = url.toString();
    } catch (e) {
      setError(getApiErrorMessage(e));
      setIsStarting(null);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 sm:px-8 lg:px-12">

      <Link
        href="/"
        className="absolute top-8 left-8 inline-flex items-center gap-1.5 text-xs opacity-60 transition-opacity hover:opacity-100"
        style={{ color: "rgba(138, 144, 178, 1)" }}
      >
        <ArrowLeft className="w-3 h-3" />
        Back to home
      </Link>


      <div className="w-full max-w-xl flex flex-col items-center text-center">

        <div className="mb-10 sm:mb-12">
          <h1 className="text-2xl sm:text-3xl lg:text-4xl tracking-tight">
            <span className="font-extrabold text-foreground">ISSUE</span>
            <span className="font-light text-foreground/75">INDEX</span>
          </h1>
        </div>


        <div className="w-full max-w-sm space-y-3 mb-8">
          <button
            type="button"
            className="btn-press btn-glow w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl text-[14px] font-medium transition-all duration-200 hover:bg-white/10 disabled:opacity-50"
            style={{
              backgroundColor: "rgba(255, 255, 255, 0.05)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              color: "rgba(230, 233, 242, 0.95)",
            }}
            disabled={isStarting !== null}
            onClick={() => startLogin("github")}
          >
            <svg className="w-5 h-5" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            {isStarting === "github" ? "Connecting..." : "Continue with GitHub"}
          </button>

          <button
            type="button"
            className="btn-press btn-glow w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl text-[14px] font-medium transition-all duration-200 hover:bg-white/10 disabled:opacity-50"
            style={{
              backgroundColor: "rgba(255, 255, 255, 0.05)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              color: "rgba(230, 233, 242, 0.95)",
            }}
            disabled={isStarting !== null}
            onClick={() => startLogin("google")}
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            {isStarting === "google" ? "Connecting..." : "Continue with Google"}
          </button>
        </div>


        <label className="flex items-center gap-2.5 cursor-pointer mb-4 rounded-lg px-2 py-1 -mx-2 transition-colors hover:bg-white/[0.03]">
          <div className="relative">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="sr-only peer"
            />
            <div
              className="w-4 h-4 rounded border transition-all peer-checked:bg-white/20 peer-checked:border-white/30"
              style={{ borderColor: "rgba(255, 255, 255, 0.15)" }}
            />
            {rememberMe && (
              <svg
                className="absolute top-0 left-0 w-4 h-4 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={3}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            )}
          </div>
          <span className="text-xs" style={{ color: "rgba(138, 144, 178, 0.7)" }}>
            Remember me for 7 days
          </span>
        </label>


        {(error ?? oauthError) && (
          <div
            className="w-full max-w-sm rounded-xl px-4 py-3 text-sm"
            style={{
              backgroundColor: "rgba(212, 24, 61, 0.12)",
              border: "1px solid rgba(212, 24, 61, 0.25)",
              color: "#f87171",
            }}
          >
            {error ?? oauthError}
          </div>
        )}
      </div>


      <div className="absolute bottom-8 left-0 right-0">
        <p className="text-center text-xs" style={{ color: "rgba(138, 144, 178, 0.6)" }}>
          By signing in, you agree to our terms of service
        </p>
      </div>
    </main>
  );
}
