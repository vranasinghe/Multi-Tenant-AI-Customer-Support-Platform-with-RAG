import { Suspense } from "react";
import type { ReactNode } from "react";

import { PageLoading } from "@/components/auth/guards";

export default function AuthLayout({ children }: { children: ReactNode }) {
  // Client components below read the URL (?next=, ?token=); Next needs a Suspense boundary.
  return <Suspense fallback={<PageLoading label="Loading…" />}>{children}</Suspense>;
}
