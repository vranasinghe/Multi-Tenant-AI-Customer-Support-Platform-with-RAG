import type { Metadata } from "next";

import { AuthCard } from "@/components/auth/auth-card";
import { InviteAcceptance } from "@/components/auth/invite-acceptance";

export const metadata: Metadata = { title: "Team invitation", referrer: "no-referrer" };

export default async function InvitePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <AuthCard title="Team invitation">
      <InviteAcceptance token={token ?? null} />
    </AuthCard>
  );
}
