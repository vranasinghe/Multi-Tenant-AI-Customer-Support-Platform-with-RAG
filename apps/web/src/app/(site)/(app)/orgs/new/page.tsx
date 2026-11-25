import type { Metadata } from "next";

import { CreateOrgForm } from "@/components/orgs/create-org-form";

export const metadata: Metadata = { title: "New organization" };

export default function NewOrgPage() {
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">New organization</h1>
      <CreateOrgForm />
    </div>
  );
}
