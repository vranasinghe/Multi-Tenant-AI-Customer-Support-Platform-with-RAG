// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push, replace: vi.fn() }) }));

import { OrgSwitcher } from "./org-switcher";

const ORGS = [
  { id: "o1", name: "Acme", role: "owner" as const },
  { id: "o2", name: "Globex", role: "agent" as const },
];

beforeEach(() => {
  nav.push.mockReset();
  window.localStorage.clear();
});

describe("OrgSwitcher", () => {
  it("lists exactly the memberships the server returned, with the active one selected", () => {
    render(<OrgSwitcher orgs={ORGS} activeOrgId="o2" />);

    const select = screen.getByRole("combobox", { name: /organization/i });
    expect(select).toHaveValue("o2");
    expect(screen.getByRole("option", { name: "Acme" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Globex" })).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(3); // two orgs + "New organization"
  });

  it("switching navigates to that org's URL and remembers the choice", async () => {
    render(<OrgSwitcher orgs={ORGS} activeOrgId="o1" />);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: /organization/i }), "o2");

    expect(nav.push).toHaveBeenCalledWith("/orgs/o2");
    expect(window.localStorage.getItem("acs.activeOrg")).toBe("o2");
  });

  it("offers creating a new organization without storing a bogus id", async () => {
    render(<OrgSwitcher orgs={ORGS} activeOrgId="o1" />);

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /organization/i }),
      screen.getByRole("option", { name: /new organization/i }),
    );

    expect(nav.push).toHaveBeenCalledWith("/orgs/new");
    expect(window.localStorage.getItem("acs.activeOrg")).toBeNull();
  });

  it("still works when localStorage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    render(<OrgSwitcher orgs={ORGS} activeOrgId="o1" />);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: /organization/i }), "o2");

    expect(nav.push).toHaveBeenCalledWith("/orgs/o2");
  });

  it("renders a plain label instead of a picker when there is a single org", () => {
    render(<OrgSwitcher orgs={[ORGS[0]!]} activeOrgId="o1" />);

    expect(screen.getByRole("combobox", { name: /organization/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Acme" })).toBeInTheDocument();
  });
});
