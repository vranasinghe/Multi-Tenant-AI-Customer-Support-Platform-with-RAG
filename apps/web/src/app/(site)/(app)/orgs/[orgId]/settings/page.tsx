"use client";

import { useRouter } from "next/navigation";

import { PageHeader } from "@/components/kit/states";
import { useOrg } from "@/components/orgs/org-provider";
import { AuditLog, RenameOrgForm, TransferOwnership } from "@/components/orgs/org-settings";
import { useAuth } from "@/lib/auth/auth-context";
import { can } from "@/lib/orgs";

export default function OrgSettingsPage() {
  const { org, setOrg, reload } = useOrg();
  const { refresh } = useAuth();
  const router = useRouter();

  return (
    <div className="grid gap-10">
      <PageHeader
        title="Organization settings"
        description="Name, activity log and ownership for this organization."
      />

      <section aria-labelledby="general-heading" className="grid gap-4">
        <h2 id="general-heading" className="text-lg font-semibold">
          General
        </h2>
        <RenameOrgForm
          key={org.name}
          org={org}
          onSaved={(updated) => {
            setOrg(updated);
            void refresh();
          }}
        />
      </section>

      {can(org, "audit:read") && (
        <section aria-labelledby="activity-heading" className="grid gap-4">
          <h2 id="activity-heading" className="text-lg font-semibold">
            Activity
          </h2>
          <AuditLog orgId={org.id} />
        </section>
      )}

      {can(org, "org:transfer") && (
        <section aria-labelledby="transfer-heading" className="grid gap-4">
          <h2 id="transfer-heading" className="text-lg font-semibold">
            Transfer ownership
          </h2>
          <TransferOwnership
            org={org}
            onTransferred={() => {
              void reload();
              router.refresh();
            }}
          />
        </section>
      )}
    </div>
  );
}
