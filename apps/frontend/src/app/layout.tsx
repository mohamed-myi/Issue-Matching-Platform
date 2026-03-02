import type { Metadata } from "next";
import { cookies } from "next/headers";
import "./globals.css";
import { Providers } from "./providers";
import { fetchBootstrapMe } from "@/lib/api/server";

export const metadata: Metadata = {
  title: {
    template: "%s | IssueIndex",
    default: "IssueIndex",
  },
  description: "Find high-quality open source issues to contribute to today.",
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "IssueIndex",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "IssueIndex Platform",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "IssueIndex",
    description: "Find high-quality open source issues to contribute to today.",
  },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const hasSession = cookieStore.has("session_id");
  const initialAuthMe = hasSession ? await fetchBootstrapMe() : null;

  return (
    <html lang="en">
      <body>
        <script
          dangerouslySetInnerHTML={{
            __html: `window.__HAS_SESSION__=${hasSession}`,
          }}
        />
        <Providers initialAuthMe={initialAuthMe}>{children}</Providers>
      </body>
    </html>
  );
}
