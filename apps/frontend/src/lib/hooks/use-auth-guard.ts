"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { useMe } from "@/lib/api/hooks";
import type { AuthMeResponse } from "@/lib/api/types";

function is401(err: unknown): boolean {
  return axios.isAxiosError(err) && err.response?.status === 401;
}

/**
 * Client-side session validity guard.
 *
 * Use this on every page that requires an authenticated session.
 */
export function useAuthGuard(initialMe?: AuthMeResponse | null) {
  const router = useRouter();
  const meQuery = useMe(initialMe);

  useEffect(() => {
    if (meQuery.isError && is401(meQuery.error)) {
      router.replace("/login");
    }
  }, [meQuery.isError, meQuery.error, router]);

  return {
    /** true while /auth/me is still in progress */
    isLoading: meQuery.isLoading,
    /** true once /auth/me succeeded */
    isAuthenticated: meQuery.isSuccess,
    /** true once /auth/me returned 401 (redirect is in progress) */
    isRedirecting: meQuery.isError && is401(meQuery.error),
    /** the raw React Query result (access .data for user info) */
    me: meQuery,
  };
}
