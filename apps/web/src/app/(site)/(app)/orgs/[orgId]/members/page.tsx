"use client";

import { PageHeader } from "@/components/kit/states";
import { MembersPanel } from "@/components/orgs/members-panel";
import { useOrg } from "@/components/orgs/org-provider";
import { useAuth } from "@/lib/auth/auth-context";

export default function MembersPage() {
  const { org } = useOrg();
  const { state } = useAuth();
  if (state.status !== "authenticated") return null;
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Team"
        description="Invite teammates and control what each person can do."
      />
      <MembersPanel org={org} currentUserId={state.user.id} />
    </div>
  );
}
