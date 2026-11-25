// @vitest-environment jsdom
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { Invitation, Member, Org, Role } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  listMembers: vi.fn(),
  listInvitations: vi.fn(),
  changeMemberRole: vi.fn(),
  removeMember: vi.fn(),
  invite: vi.fn(),
  resendInvitation: vi.fn(),
  revokeInvitation: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: vi.fn() }),
}));

import { MembersPanel } from "./members-panel";

const PERMISSIONS: Record<Role, string[]> = {
  owner: ["org:read", "member:read", "member:invite", "member:manage", "org:transfer"],
  admin: ["org:read", "member:read", "member:invite", "member:manage"],
  agent: ["org:read", "member:read"],
  viewer: ["org:read", "member:read"],
};
const orgAs = (role: Role): Org => ({
  id: "o1",
  name: "Acme",
  slug: "acme",
  status: "active",
  role,
  permissions: PERMISSIONS[role],
  settings: {},
  created_at: "2026-11-22T00:00:00Z",
});
const member = (id: string, name: string, role: Role): Member => ({
  id,
  role,
  created_at: "2026-11-22T00:00:00Z",
  user: { id: `u-${id}`, name, email: `${name.toLowerCase()}@acme.com`, email_verified: true },
});
const MEMBERS = [
  member("m1", "Olivia", "owner"),
  member("m2", "Adam", "admin"),
  member("m3", "Alex", "agent"),
];
const INVITES: Invitation[] = [
  {
    id: "i1",
    email: "new@acme.com",
    role: "viewer",
    status: "pending",
    expires_at: "2026-11-29T00:00:00Z",
    created_at: "2026-11-22T00:00:00Z",
  },
];

function renderPanel(role: Role, currentUserId: string) {
  return render(<MembersPanel org={orgAs(role)} currentUserId={currentUserId} />);
}
const row = (name: string) => screen.getByRole("row", { name: new RegExp(name, "i") });

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset());
  mocks.listMembers.mockResolvedValue({ data: MEMBERS });
  mocks.listInvitations.mockResolvedValue({ data: INVITES });
});

describe("MembersPanel permissions", () => {
  it("shows an agent the member list but no management controls", async () => {
    renderPanel("agent", "u-m3");

    await screen.findByText("Olivia");

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^remove/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /invite/i })).not.toBeInTheDocument();
    expect(mocks.listInvitations).not.toHaveBeenCalled(); // not even requested without permission
    expect(within(row("Alex")).getByRole("button", { name: /leave/i })).toBeInTheDocument();
  });

  it("lets an admin manage non-owners but never offers controls on the owner or on themself", async () => {
    renderPanel("admin", "u-m2");
    await screen.findByText("Olivia");

    expect(within(row("Alex")).getByRole("combobox", { name: /role for alex/i })).toBeEnabled();
    expect(within(row("Alex")).getByRole("button", { name: /remove alex/i })).toBeInTheDocument();
    expect(within(row("Olivia")).queryByRole("combobox")).not.toBeInTheDocument();
    expect(
      within(row("Olivia")).queryByRole("button", { name: /remove/i }),
    ).not.toBeInTheDocument();
    expect(within(row("Adam")).queryByRole("combobox")).not.toBeInTheDocument(); // own role
  });

  it("never offers 'owner' as a role to assign or to invite", async () => {
    renderPanel("owner", "u-m1");
    await screen.findByText("Alex");

    const roleSelect = within(row("Alex")).getByRole("combobox", { name: /role for alex/i });
    expect(within(roleSelect).queryByRole("option", { name: /owner/i })).not.toBeInTheDocument();
    const inviteRole = screen.getByRole("combobox", { name: /^role$/i });
    expect(within(inviteRole).queryByRole("option", { name: /owner/i })).not.toBeInTheDocument();
  });
});

describe("MembersPanel actions", () => {
  it("changes a role through the API and reflects it", async () => {
    mocks.changeMemberRole.mockResolvedValue({ ...MEMBERS[2], role: "viewer" });
    renderPanel("admin", "u-m2");
    await screen.findByText("Alex");

    await userEvent.selectOptions(
      within(row("Alex")).getByRole("combobox", { name: /role for alex/i }),
      "viewer",
    );

    expect(mocks.changeMemberRole).toHaveBeenCalledWith("o1", "m3", "viewer");
    await waitFor(() =>
      expect(within(row("Alex")).getByRole("combobox", { name: /role for alex/i })).toHaveValue(
        "viewer",
      ),
    );
  });

  it("surfaces a server refusal and restores the previous role", async () => {
    mocks.changeMemberRole.mockRejectedValue(
      new ApiError({ status: 403, code: "forbidden", message: "no" }),
    );
    renderPanel("admin", "u-m2");
    await screen.findByText("Alex");

    await userEvent.selectOptions(
      within(row("Alex")).getByRole("combobox", { name: /role for alex/i }),
      "admin",
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/don't have permission/i);
    expect(within(row("Alex")).getByRole("combobox", { name: /role for alex/i })).toHaveValue(
      "agent",
    );
  });

  it("requires explicit confirmation before removing someone", async () => {
    mocks.removeMember.mockResolvedValue(undefined);
    renderPanel("admin", "u-m2");
    await screen.findByText("Alex");

    await userEvent.click(within(row("Alex")).getByRole("button", { name: /remove alex/i }));
    expect(mocks.removeMember).not.toHaveBeenCalled();
    await userEvent.click(within(row("Alex")).getByRole("button", { name: /confirm remove/i }));

    expect(mocks.removeMember).toHaveBeenCalledWith("o1", "m3");
    await waitFor(() => expect(screen.queryByText("Alex")).not.toBeInTheDocument());
  });

  it("can cancel a removal", async () => {
    renderPanel("admin", "u-m2");
    await screen.findByText("Alex");

    await userEvent.click(within(row("Alex")).getByRole("button", { name: /remove alex/i }));
    await userEvent.click(within(row("Alex")).getByRole("button", { name: /cancel/i }));

    expect(mocks.removeMember).not.toHaveBeenCalled();
    expect(within(row("Alex")).getByRole("button", { name: /remove alex/i })).toBeInTheDocument();
  });

  it("explains the last-owner rule when the sole owner tries to leave", async () => {
    mocks.removeMember.mockRejectedValue(
      new ApiError({ status: 409, code: "last_owner", message: "x" }),
    );
    renderPanel("owner", "u-m1");
    await screen.findByText("Olivia");

    await userEvent.click(within(row("Olivia")).getByRole("button", { name: /leave/i }));
    await userEvent.click(within(row("Olivia")).getByRole("button", { name: /confirm leave/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/at least one owner/i);
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("returns to the dashboard after leaving", async () => {
    mocks.removeMember.mockResolvedValue(undefined);
    renderPanel("agent", "u-m3");
    await screen.findByText("Alex");

    await userEvent.click(within(row("Alex")).getByRole("button", { name: /leave/i }));
    await userEvent.click(within(row("Alex")).getByRole("button", { name: /confirm leave/i }));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/dashboard"));
  });
});

describe("MembersPanel invitations", () => {
  it("validates the email, then invites with the chosen role", async () => {
    mocks.invite.mockResolvedValue({ ...INVITES[0], email: "sam@acme.com", role: "agent" });
    renderPanel("admin", "u-m2");
    await screen.findByText("Alex");
    const form = screen.getByRole("form", { name: /invite/i });

    await userEvent.click(within(form).getByRole("button", { name: /send invitation/i }));
    expect(await within(form).findByText("Enter your email address.")).toBeInTheDocument();
    expect(mocks.invite).not.toHaveBeenCalled();

    await userEvent.type(within(form).getByLabelText(/email/i), "sam@acme.com");
    await userEvent.selectOptions(within(form).getByRole("combobox", { name: /^role$/i }), "agent");
    await userEvent.click(within(form).getByRole("button", { name: /send invitation/i }));

    expect(mocks.invite).toHaveBeenCalledWith("o1", { email: "sam@acme.com", role: "agent" });
    expect(await screen.findByRole("status")).toHaveTextContent(/invitation sent to sam@acme.com/i);
  });

  it("reports an already-member conflict clearly", async () => {
    mocks.invite.mockRejectedValue(
      new ApiError({ status: 409, code: "already_member", message: "x" }),
    );
    renderPanel("admin", "u-m2");
    await screen.findByText("Alex");
    const form = screen.getByRole("form", { name: /invite/i });

    await userEvent.type(within(form).getByLabelText(/email/i), "alex@acme.com");
    await userEvent.click(within(form).getByRole("button", { name: /send invitation/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already a member/i);
  });

  it("lists pending invitations and can revoke one", async () => {
    mocks.revokeInvitation.mockResolvedValue(undefined);
    renderPanel("admin", "u-m2");
    await screen.findByText("new@acme.com");

    await userEvent.click(
      screen.getByRole("button", { name: /revoke invitation for new@acme.com/i }),
    );

    expect(mocks.revokeInvitation).toHaveBeenCalledWith("o1", "i1");
    await waitFor(() => expect(screen.queryByText("new@acme.com")).not.toBeInTheDocument());
  });
});
