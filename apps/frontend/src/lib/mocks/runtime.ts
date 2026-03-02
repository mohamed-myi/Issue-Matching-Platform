let mockInitPromise: Promise<void> | null = null;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function isMockApiEnabled(): boolean {
  return process.env.NEXT_PUBLIC_MOCK_API === "true";
}

async function startMocks(): Promise<void> {
  if (!isBrowser() || !isMockApiEnabled()) {
    return;
  }

  const { initMocks } = await import("@/mocks");
  await initMocks();
}

export async function ensureMockApiReady(): Promise<void> {
  if (!isBrowser() || !isMockApiEnabled()) {
    return;
  }

  if (!mockInitPromise) {
    mockInitPromise = startMocks().catch((error) => {
      // Fail open in development so the UI is usable even if MSW cannot start.
      console.error("[MSW] Failed to initialize mock worker:", error);
    });
  }

  await mockInitPromise;
}

export function resetMockInitForTesting(): void {
  mockInitPromise = null;
}
