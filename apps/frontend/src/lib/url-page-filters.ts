import type { BootstrapFilters } from "@/lib/api/server";

export type PageSearchParams = Record<string, string | string[] | undefined>;

export function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function buildFilters(params: PageSearchParams): BootstrapFilters {
  const lang = firstValue(params.lang);
  const label = firstValue(params.label);
  const repo = firstValue(params.repo);

  return {
    languages: lang ? [lang] : undefined,
    labels: label ? [label] : undefined,
    repos: repo ? [repo] : undefined,
  };
}

