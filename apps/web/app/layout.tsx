import type { Metadata, Viewport } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";
import { SessionProvider } from "@/lib/session";
import { caveat, manrope, stix } from "./fonts";

export const metadata: Metadata = {
  title: { template: "%s · Slate", default: "Slate" },
  description: "Study math from your own course materials: narrated board lessons and practice that adapts to what you miss.",
};

export const viewport: Viewport = {
  themeColor: "#0f1115",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${manrope.variable} ${stix.variable} ${caveat.variable}`}>
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
