"use client";

import type { ReactNode } from "react";
import { useRequireUser } from "@/lib/session";
import { AppShell } from "./AppShell";
import { Spinner } from "./Spinner";

/** App chrome for signed-in pages; signed-out visitors are sent to /login. */
export function SignedInShell({ children }: { children: ReactNode }) {
  const { user, loading } = useRequireUser();
  if (loading || !user) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner label={loading ? "Loading" : "Redirecting to sign in"} />
      </div>
    );
  }
  return <AppShell userName={user.display_name}>{children}</AppShell>;
}
