import ProfileClient from "./profile-client";
import { Suspense } from "react";
import { PageLoadingFallback } from "@/components/common/PageLoadingFallback";

export const dynamic = "force-dynamic";

export default async function ProfilePage({
  searchParams,
}: {
  searchParams?: Promise<{ tab?: string; connected?: string; error?: string }>;
}) {
  const resolvedParams = searchParams ? await searchParams : undefined;
  const tab = resolvedParams?.tab ?? "overview";
  const connected = resolvedParams?.connected ?? null;
  const error = resolvedParams?.error ?? null;

  return (
    <Suspense fallback={<PageLoadingFallback />}>
      <ProfileClient initialTab={tab} connected={connected} initialError={error} />
    </Suspense>
  );
}
