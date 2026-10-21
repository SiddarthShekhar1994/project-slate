"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";
import type { User } from "./types";

type SessionState = { user: User | null; loading: boolean; refresh: () => Promise<void>; signOut: () => Promise<void> };

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser((await api.session()).user);
    } catch (error) {
      console.error(error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .session()
      .then(({ user }) => !cancelled && setUser(user))
      .catch((error) => {
        console.error(error);
        if (!cancelled) setUser(null);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  return <SessionContext.Provider value={{ user, loading, refresh, signOut }}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}

/** Send signed-out visitors to /login and bring them back afterwards. */
export function useRequireUser(): SessionState {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => {
    if (!session.loading && !session.user) {
      const query = search?.toString();
      const next = `${pathname}${query ? `?${query}` : ""}`;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [session.loading, session.user, router, pathname, search]);
  return session;
}
