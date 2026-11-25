"use client";

import { useRouter } from "next/navigation";
import type { ChangeEvent } from "react";

import { Select } from "@acs/ui/components/select";

import { storeOrgId } from "@/lib/orgs";

const NEW_ORG = "__new__";

/**
 * Switching organizations is just navigation to `/orgs/{id}`: there is no server-side "current
 * org", and every request re-verifies membership for the id in its URL. The options come from
 * the server's own membership list, never from storage or user input.
 */
export function OrgSwitcher({
  orgs,
  activeOrgId,
  className = "w-48 max-w-full",
}: {
  orgs: readonly { id: string; name: string }[];
  activeOrgId: string | null;
  className?: string;
}) {
  const router = useRouter();

  function onChange(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.target.value;
    if (value === NEW_ORG) {
      router.push("/orgs/new");
      return;
    }
    storeOrgId(value);
    router.push(`/orgs/${encodeURIComponent(value)}`);
  }

  return (
    <Select
      aria-label="Organization"
      value={activeOrgId ?? ""}
      onChange={onChange}
      className={className}
    >
      {activeOrgId === null && (
        <option value="" disabled>
          Choose organization
        </option>
      )}
      {orgs.map((org) => (
        <option key={org.id} value={org.id}>
          {org.name}
        </option>
      ))}
      <option value={NEW_ORG}>New organization…</option>
    </Select>
  );
}
