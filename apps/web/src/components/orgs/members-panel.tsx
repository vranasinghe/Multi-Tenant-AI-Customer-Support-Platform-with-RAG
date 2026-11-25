"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Label } from "@acs/ui/components/label";
import { Select } from "@acs/ui/components/select";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { AssignableRole, Invitation, Member, Org } from "@/lib/api/types";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";
import { fieldErrorsFromZod, inviteSchema } from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

import { TextField } from "../form/text-field";

const ASSIGNABLE: readonly AssignableRole[] = ["admin", "agent", "viewer"];
const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  agent: "Agent",
  viewer: "Viewer",
};

/**
 * Members and invitations. Controls are shown only when the server-provided permission list
 * allows them, but this is presentation: the API re-checks role, target and last-owner rules on
 * every call and these buttons surface its refusals.
 */
export function MembersPanel({ org, currentUserId }: { org: Org; currentUserId: string }) {
  const router = useRouter();
  const orgId = org.id;
  const canManage = can(org, "member:manage");
  const canInvite = can(org, "member:invite");

  const [actionError, setActionError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const {
    data,
    error: loadError,
    reload,
    update,
  } = useAsyncData(async () => {
    const [memberPage, invitationPage] = await Promise.all([
      api.listMembers(orgId),
      // Don't even ask for invitations unless the role may see them.
      canInvite ? api.listInvitations(orgId) : Promise.resolve({ data: [] as Invitation[] }),
    ]);
    return { members: memberPage.data, invitations: invitationPage.data };
  }, [orgId, canInvite]);

  const members = data?.members ?? null;
  const invitations = data?.invitations ?? [];
  const setMembers = (change: (current: Member[]) => Member[]) =>
    update((state) => state && { ...state, members: change(state.members) });
  const setInvitations = (change: (current: Invitation[]) => Invitation[]) =>
    update((state) => state && { ...state, invitations: change(state.invitations) });

  async function changeRole(member: Member, role: AssignableRole) {
    setActionError(null);
    try {
      const updated = await api.changeMemberRole(orgId, member.id, role);
      setMembers((current) =>
        current.map((m) => (m.id === member.id ? { ...m, role: updated.role } : m)),
      );
    } catch (error) {
      setActionError(describeApiError(error));
    }
  }

  async function removeMember(member: Member) {
    setActionError(null);
    const leaving = member.user.id === currentUserId;
    try {
      await api.removeMember(orgId, member.id);
      setConfirming(null);
      if (leaving) {
        router.replace("/dashboard");
        return;
      }
      setMembers((current) => current.filter((m) => m.id !== member.id));
    } catch (error) {
      setConfirming(null);
      setActionError(describeApiError(error));
    }
  }

  async function revoke(invitation: Invitation) {
    setActionError(null);
    try {
      await api.revokeInvitation(orgId, invitation.id);
      setInvitations((current) => current.filter((i) => i.id !== invitation.id));
    } catch (error) {
      setActionError(describeApiError(error));
    }
  }

  async function resend(invitation: Invitation) {
    setActionError(null);
    try {
      const updated = await api.resendInvitation(orgId, invitation.id);
      setInvitations((current) => current.map((i) => (i.id === invitation.id ? updated : i)));
    } catch (error) {
      setActionError(describeApiError(error));
    }
  }

  if (loadError) {
    return (
      <div className="grid gap-3">
        <Alert variant="destructive">{loadError}</Alert>
        <Button variant="outline" className="justify-self-start" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }
  if (members === null) {
    return <p className="text-sm text-muted-foreground">Loading members…</p>;
  }

  return (
    <div className="grid gap-10">
      {actionError && <Alert variant="destructive">{actionError}</Alert>}

      <section aria-labelledby="members-heading" className="grid gap-3">
        <h2 id="members-heading" className="text-lg font-semibold">
          Members <span className="font-normal text-muted-foreground">({members.length})</span>
        </h2>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-muted/40 text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">
                  Member
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Role
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {members.map((member) => {
                const isSelf = member.user.id === currentUserId;
                const managesThis =
                  canManage && !isSelf && (member.role !== "owner" || org.role === "owner");
                const confirmingThis = confirming === member.id;
                const verb = isSelf ? "leave" : "remove";
                return (
                  <tr key={member.id}>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="font-medium">{member.user.name}</span>
                        {isSelf && <span className="text-muted-foreground">(you)</span>}
                      </div>
                      <div className="text-muted-foreground">{member.user.email}</div>
                    </td>
                    <td className="px-4 py-3">
                      {managesThis ? (
                        <Select
                          aria-label={`Role for ${member.user.name}`}
                          value={member.role}
                          onChange={(event) =>
                            void changeRole(member, event.target.value as AssignableRole)
                          }
                          className="w-32"
                        >
                          {member.role === "owner" && (
                            <option value="owner" disabled>
                              {ROLE_LABEL.owner}
                            </option>
                          )}
                          {ASSIGNABLE.map((role) => (
                            <option key={role} value={role}>
                              {ROLE_LABEL[role]}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        ROLE_LABEL[member.role]
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {(managesThis || isSelf) &&
                        (confirmingThis ? (
                          <span className="inline-flex gap-2">
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => void removeMember(member)}
                            >
                              Confirm {verb}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                              Cancel
                            </Button>
                          </span>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            aria-label={isSelf ? "Leave" : `Remove ${member.user.name}`}
                            onClick={() => setConfirming(member.id)}
                          >
                            {isSelf ? "Leave" : "Remove"}
                          </Button>
                        ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {canInvite && (
        <InviteSection
          orgId={orgId}
          invitations={invitations}
          onInvited={(invitation) =>
            setInvitations((current) => [
              invitation,
              ...current.filter((i) => i.id !== invitation.id),
            ])
          }
          onRevoke={revoke}
          onResend={resend}
        />
      )}
    </div>
  );
}

function InviteSection({
  orgId,
  invitations,
  onInvited,
  onRevoke,
  onResend,
}: {
  orgId: string;
  invitations: Invitation[];
  onInvited: (invitation: Invitation) => void;
  onRevoke: (invitation: Invitation) => Promise<void>;
  onResend: (invitation: Invitation) => Promise<void>;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<AssignableRole>("agent");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setFormError(null);
    setSentTo(null);

    const parsed = inviteSchema.safeParse({ email, role });
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});

    setPending(true);
    try {
      const invitation = await api.invite(orgId, parsed.data);
      onInvited(invitation);
      setSentTo(parsed.data.email);
      setEmail("");
    } catch (error) {
      setFormError(describeApiError(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="invite-heading" className="grid gap-4">
      <h2 id="invite-heading" className="text-lg font-semibold">
        Invite a teammate
      </h2>
      <form
        ref={formRef}
        aria-label="Invite a teammate"
        onSubmit={onSubmit}
        noValidate
        className="grid max-w-xl gap-4"
      >
        {formError && <Alert variant="destructive">{formError}</Alert>}
        {sentTo && (
          <Alert variant="success">Invitation sent to {sentTo}. The link expires in 7 days.</Alert>
        )}
        <div className="grid gap-4 sm:grid-cols-[1fr_9rem]">
          <TextField
            label="Email"
            type="email"
            name="email"
            autoComplete="off"
            inputMode="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            error={errors.email}
          />
          <div className="grid content-start gap-1.5">
            <Label htmlFor="invite-role">Role</Label>
            <Select
              id="invite-role"
              value={role}
              onChange={(event) => setRole(event.target.value as AssignableRole)}
            >
              {ASSIGNABLE.map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABEL[value]}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <Button type="submit" disabled={pending} className="justify-self-start">
          {pending ? "Sending…" : "Send invitation"}
        </Button>
      </form>

      {invitations.length > 0 && (
        <div className="grid gap-2">
          <h3 className="text-sm font-medium text-muted-foreground">Pending invitations</h3>
          <ul className="divide-y rounded-md border">
            {invitations.map((invitation) => (
              <li
                key={invitation.id}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
              >
                <div>
                  <span className="font-medium">{invitation.email}</span>{" "}
                  <span className="text-muted-foreground">
                    · {ROLE_LABEL[invitation.role]}
                    {invitation.status === "expired" && " · expired"}
                  </span>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label={`Resend invitation for ${invitation.email}`}
                    onClick={() => void onResend(invitation)}
                  >
                    Resend
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Revoke invitation for ${invitation.email}`}
                    onClick={() => void onRevoke(invitation)}
                  >
                    Revoke
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
