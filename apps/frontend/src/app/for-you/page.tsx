import { Suspense } from "react";
import ForYouClient from "./client";
import { fetchBootstrapFeed, fetchBootstrapSearch } from "@/lib/api/server";
import { PageLoadingFallback } from "@/components/common/PageLoadingFallback";
import { buildFilters, firstValue, type PageSearchParams } from "@/lib/url-page-filters";

export const dynamic = "force-dynamic";

export default async function ForYouPage({
  searchParams,
}: {
  searchParams?: Promise<PageSearchParams>;
}) {
  const params = (await searchParams) ?? {};
  const q = (firstValue(params.q) ?? "").trim();
  const filters = buildFilters(params);

  const [initialSearchPage, initialFeedPage] = await Promise.all([
    q ? fetchBootstrapSearch({ query: q, pageSize: 20, filters }) : Promise.resolve(null),
    q ? Promise.resolve(null) : fetchBootstrapFeed({ pageSize: 20, filters }),
  ]);

  return (
    <Suspense fallback={<PageLoadingFallback />}>
      <ForYouClient
        initialSearchPage={initialSearchPage}
        initialFeedPage={initialFeedPage}
      />
    </Suspense>
  );
}
