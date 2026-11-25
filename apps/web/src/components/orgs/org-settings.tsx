"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Label } from "@acs/ui/components/label";
import { Select } from "@acs/ui/components/select";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { AuditEntry, Member, Org } from "@/lib/api/types";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";
import { fieldErrorsFromZod, orgNameSchema } from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

import { TextField, useFocusFirstInvalid } from "../form/text-field";

export function RenameOrgForm({ org, onSaved }: { org: Org; onSaved: (org: Org) => void }) {
  const formRef = useRef<HTMLFormElement>(null);
  const editable = can(org, "org:update");
  const [name, setName] = useState(org.name);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  useFocusFirstInvalid(formRef, errors);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending || !editable) return;
    setMessage(null);
    const parsed = orgNameSchema.safeParse({ name });
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});
    setPending(true);
    try {
      onSaved(await api.updateOrg(org.id, { name: parsed.data.name }));
      setMessage({ kind: "ok", text: "Saved." });
    } catch (error) {
      setMessage({ kind: "error", text: describeApiError(error) });
    } finally {
      setPending(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate className="grid max-w-sm gap-4">
      {message && (
        <Alert variant={message.kind === "ok" ? "success" : "destructive"}>{message.text}</Alert>
      )}
      <TextField
        label="Organization name"
        name="organization"
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={errors.name}
        disabled={!editable}
        hint={editable ? undefined : "Only owners and admins can rename the organization."}
      />
      {editable && (
        <Button type="submit" disabled={pending} className="justify-self-start">
          {pending ? "Saving…" : "Save"}
        </Button>
      )}
    </form>
  );
}

/** Owner-only. Requires the owner's password again and an admin to hand ownership to. */
export function TransferOwnership({ org, onTransferred }: { org: Org; onTransferred: () => void }) {
  const [admins, setAdmins] = useState<Member[]>([]);
  const [target, setTarget] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listMembers(org.id)
      .then((page) => !cancelled && setAdmins(page.data.filter((m) => m.role === "admin")))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [org.id]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    if (!target || !password) {
      setError("Choose an admin and enter your password.");
      return;
    }
    setError(null);
    setPending(true);
    try {
      await api.transferOwnership(org.id, { new_owner_user_id: target, password });
      onTransferred();
    } catch (failure) {
      setError(describeApiError(failure));
      setPassword("");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Transfer ownership"
      className="grid max-w-sm gap-4"
    >
      {error && <Alert variant="destructive">{error}</Alert>}
      {admins.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Ownership can only pass to an admin. Promote a member to admin first.
        </p>
      ) : (
        <>
          <div className="grid gap-1.5">
            <Label htmlFor="new-owner">New owner</Label>
            <Select
              id="new-owner"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            >
              <option value="">Choose an admin…</option>
              {admins.map((member) => (
                <option key={member.id} value={member.user.id}>
                  {member.user.name} ({member.user.email})
                </option>
              ))}
            </Select>
          </div>
          <TextField
            label="Your password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            hint="You'll become an admin. Only the new owner can undo this."
          />
          <Button
            type="submit"
            variant="destructive"
            disabled={pending}
            className="justify-self-start"
          >
            {pending ? "Transferring…" : "Transfer ownership"}
          </Button>
        </>
      )}
    </form>
  );
}

const ACTION_LABEL: Record<string, string> = {
  "org.created": "Organization created",
  "org.updated": "Organization updated",
  "member.invited": "Member invited",
  "invitation.resent": "Invitation resent",
  "invitation.revoked": "Invitation revoked",
  "invitation.accepted": "Invitation accepted",
  "member.role_changed": "Role changed",
  "member.removed": "Member removed",
  "member.left": "Member left",
  "org.ownership_transferred": "Ownership transferred",
};

function describeMetadata(entry: AuditEntry): string {
  const m = entry.metadata;
  if (entry.action === "member.role_changed") return `${String(m.from)} → ${String(m.to)}`;
  if (typeof m.email === "string") return m.email;
  return "";
}

export function AuditLog({ orgId }: { orgId: string }) {
  const { data, error: loadError, update } = useAsyncData(() => api.listAuditLogs(orgId), [orgId]);
  const [moreError, setMoreError] = useState<string | null>(null);
  const entries: AuditEntry[] | null = data?.data ?? null;
  const cursor = data?.has_more ? data.next_cursor : null;

  async function loadMore(next: string) {
    setMoreError(null);
    try {
      const page = await api.listAuditLogs(orgId, next);
      update((state) => state && { ...page, data: [...state.data, ...page.data] });
    } catch (failure) {
      setMoreError(describeApiError(failure));
    }
  }

  if (loadError && entries === null) return <Alert variant="destructive">{loadError}</Alert>;
  if (entries === null) return <p className="text-sm text-muted-foreground">Loading activity…</p>;
  return (
    <div className="grid gap-3">
      <ul className="divide-y rounded-md border text-sm">
        {entries.map((entry) => (
          <li
            key={entry.id}
            className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3"
          >
            <div>
              <span className="font-medium">{ACTION_LABEL[entry.action] ?? entry.action}</span>
              {describeMetadata(entry) && (
                <span className="text-muted-foreground"> · {describeMetadata(entry)}</span>
              )}
              <div className="text-muted-foreground">
                by {entry.actor?.name ?? entry.actor_type}
              </div>
            </div>
            <time dateTime={entry.created_at} className="text-muted-foreground tabular-nums">
              {new Date(entry.created_at).toLocaleString()}
            </time>
          </li>
        ))}
      </ul>
      {moreError && <Alert variant="destructive">{moreError}</Alert>}
      {cursor && (
        <Button
          variant="outline"
          className="justify-self-start"
          onClick={() => void loadMore(cursor)}
        >
          Load more
        </Button>
      )}
    </div>
  );
}
