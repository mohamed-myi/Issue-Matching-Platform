import { cookies } from "next/headers";
import { getApiBaseUrl } from "./base-url";
import type {
  AuthMeResponse,
  FeedResponse,
  SearchResponse,
  TrendingResponse,
} from "./types";

export type BootstrapFilters = {
  languages?: string[];
  labels?: string[];
  repos?: string[];
};

type RequestOptions = {
  method?: "GET" | "POST";
  params?: Record<string, string | number | string[] | undefined>;
  body?: unknown;
  includeCookies?: boolean;
};

function shouldSkipServerBootstrap(): boolean {
  return process.env.NEXT_PUBLIC_MOCK_API === "true";
}

function buildBootstrapListParams(
  pageSize: number,
  filters?: BootstrapFilters,
): Record<string, string | number | string[] | undefined> {
  return {
    page: 1,
    page_size: pageSize,
    languages: filters?.languages,
    labels: filters?.labels,
    repos: filters?.repos,
  };
}

function buildUrl(path: string, params?: RequestOptions["params"]): string | null {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    return null;
  }

  const url = new URL(path, `${baseUrl}/`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined) continue;
      if (Array.isArray(value)) {
        for (const item of value) {
          url.searchParams.append(key, item);
        }
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function cookieHeaderValue(): Promise<string | null> {
  const cookieStore = await cookies();
  const pairs = cookieStore.getAll().map(({ name, value }) => `${name}=${value}`);
  return pairs.length > 0 ? pairs.join("; ") : null;
}

async function fetchApiJson<T>(path: string, options: RequestOptions = {}): Promise<T | null> {
  if (shouldSkipServerBootstrap()) {
    return null;
  }

  const url = buildUrl(path, options.params);
  if (!url) {
    return null;
  }

  const headers: Record<string, string> = {};
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.includeCookies) {
    const cookieHeader = await cookieHeaderValue();
    if (cookieHeader) {
      headers.cookie = cookieHeader;
    }
  }

  try {
    const response = await fetch(url, {
      method: options.method ?? "GET",
      cache: "no-store",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function fetchBootstrapMe(): Promise<AuthMeResponse | null> {
  return fetchApiJson<AuthMeResponse>("auth/me", { includeCookies: true });
}

export async function fetchBootstrapTrending(params: {
  pageSize?: number;
  filters?: BootstrapFilters;
}): Promise<TrendingResponse | null> {
  const { pageSize = 20, filters } = params;
  return fetchApiJson<TrendingResponse>("feed/trending", {
    params: buildBootstrapListParams(pageSize, filters),
  });
}

export async function fetchBootstrapFeed(params: {
  pageSize?: number;
  filters?: BootstrapFilters;
}): Promise<FeedResponse | null> {
  const { pageSize = 20, filters } = params;
  return fetchApiJson<FeedResponse>("feed", {
    includeCookies: true,
    params: buildBootstrapListParams(pageSize, filters),
  });
}

export async function fetchBootstrapSearch(params: {
  query: string;
  pageSize?: number;
  filters?: BootstrapFilters;
}): Promise<SearchResponse | null> {
  const { query, pageSize = 20, filters } = params;
  return fetchApiJson<SearchResponse>("search", {
    method: "POST",
    body: {
      query,
      page: 1,
      page_size: pageSize,
      filters: {
        languages: filters?.languages ?? [],
        labels: filters?.labels ?? [],
        repos: filters?.repos ?? [],
      },
    },
    includeCookies: true,
  });
}
