// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { isNavItemActive } from "../app-shell";
import { ConfirmDialog } from "./confirm-dialog";
import { ComingSoon, EmptyState, ErrorState } from "./states";
import { ToastProvider, useToast } from "./toast";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => "/",
}));

function ConfirmHarness({ onConfirm }: { onConfirm: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Delete it?"
        description="This can't be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          await onConfirm();
          setOpen(false);
        }}
      />
    </>
  );
}

describe("ConfirmDialog", () => {
  it("focuses Cancel first, closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<ConfirmHarness onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("alertdialog", { name: "Delete it?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Open" })).toHaveFocus());
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("disables both buttons while the action runs", async () => {
    const user = userEvent.setup();
    let finish: () => void = () => {};
    const onConfirm = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    render(<ConfirmHarness onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await act(async () => finish());
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});

function ToastButton() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.success("Saved", "All good")}>ok</button>
      <button onClick={() => toast.error("Failed")}>fail</button>
    </>
  );
}

describe("Toasts", () => {
  it("announces success politely and errors assertively, and can be dismissed", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <ToastButton />
      </ToastProvider>,
    );

    await user.click(screen.getByRole("button", { name: "ok" }));
    await user.click(screen.getByRole("button", { name: "fail" }));

    expect(screen.getByRole("status")).toHaveTextContent("SavedAll good");
    expect(screen.getByRole("alert")).toHaveTextContent("Failed");
    await user.click(screen.getAllByRole("button", { name: "Dismiss notification" })[0]!);
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  });

  it("dismisses itself after a few seconds", () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <ToastButton />
        </ToastProvider>,
      );
      act(() => screen.getByRole("button", { name: "ok" }).click());
      expect(screen.getByText("Saved")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(5_100));
      expect(screen.queryByText("Saved")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("state components", () => {
  it("renders empty, error and coming-soon states with their labels", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(
      <>
        <EmptyState title="Nothing here" description="Add something." />
        <ErrorState message="Boom" onRetry={retry} />
        <ComingSoon title="Billing" phase="Billing phase" description="Later." />
      </>,
    );

    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.getByRole("region", { name: "Billing (coming soon)" })).toHaveTextContent(
      "Coming soon · Billing phase",
    );
  });
});

describe("isNavItemActive", () => {
  const base = "/orgs/o1";
  it("matches overview exactly and sections by prefix", () => {
    expect(isNavItemActive("/orgs/o1", base, "")).toBe(true);
    expect(isNavItemActive("/orgs/o1/chatbots", base, "")).toBe(false);
    expect(isNavItemActive("/orgs/o1/chatbots/b1", base, "/chatbots")).toBe(true);
    expect(isNavItemActive("/orgs/o1/chatbots-old", base, "/chatbots")).toBe(false);
  });
});
