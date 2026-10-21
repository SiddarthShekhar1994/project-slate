import { type ReactNode, Suspense } from "react";
import { SignedInShell } from "@/components/shared/ui/SignedInShell";
import { Spinner } from "@/components/shared/ui/Spinner";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="p-8"><Spinner /></div>}>
      <SignedInShell>{children}</SignedInShell>
    </Suspense>
  );
}
