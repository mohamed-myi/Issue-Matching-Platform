"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PropsWithChildren, useEffect, useState } from "react";
import type { AuthMeResponse } from "@/lib/api/types";
import { ensureMockApiReady } from "@/lib/mocks/runtime";

type ProvidersProps = PropsWithChildren<{
  initialAuthMe?: AuthMeResponse | null;
}>;

export function Providers({ children, initialAuthMe = null }: ProvidersProps) {
  const [queryClient] = useState(
    () => {
      const client = new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 1000 * 60,
            refetchOnWindowFocus: false,
          },
        },
      });

      if (initialAuthMe) {
        client.setQueryData(["auth", "me"], initialAuthMe);
      }

      return client;
    },
  );
  useEffect(() => {
    void ensureMockApiReady();
  }, []);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
