import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth/auth-context";

/** Everything except the dev status page lives under the auth provider. */
export default function SiteLayout({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
