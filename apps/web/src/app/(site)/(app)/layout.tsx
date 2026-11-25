import { Suspense } from "react";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { PageLoading, RequireAuth } from "@/components/auth/guards";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<PageLoading label="Loading…" />}>
      <RequireAuth>
        <AppShell>{children}</AppShell>
      </RequireAuth>
    </Suspense>
  );
}
