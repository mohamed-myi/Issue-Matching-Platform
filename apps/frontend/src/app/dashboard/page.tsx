import { Suspense } from "react";
import DashboardClient from "./client";
import { fetchBootstrapSearch, fetchBootstrapTrending } from "@/lib/api/server";
import { PageLoadingFallback } from "@/components/common/PageLoadingFallback";
import { buildFilters, firstValue, type PageSearchParams } from "@/lib/url-page-filters";

export const dynamic = "force-dynamic";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams?: Promise<PageSearchParams>;
}) {
  const params = (await searchParams) ?? {};
  const q = (firstValue(params.q) ?? "").trim();
  const filters = buildFilters(params);

  const [initialSearchPage, initialTrendingPage] = await Promise.all([
    q ? fetchBootstrapSearch({ query: q, pageSize: 20, filters }) : Promise.resolve(null),
    q ? Promise.resolve(null) : fetchBootstrapTrending({ pageSize: 20, filters }),
  ]);

  return (
    <Suspense fallback={<PageLoadingFallback />}>
      <DashboardClient
        initialSearchPage={initialSearchPage}
        initialTrendingPage={initialTrendingPage}
      />
    </Suspense>
  );
}
