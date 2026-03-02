import { Suspense } from "react";
import SavedClient from "./client";
import { PageLoadingFallback } from "@/components/common/PageLoadingFallback";

export const dynamic = "force-dynamic";

export default function SavedPage() {
  return (
    <Suspense fallback={<PageLoadingFallback />}>
      <SavedClient />
    </Suspense>
  );
}
