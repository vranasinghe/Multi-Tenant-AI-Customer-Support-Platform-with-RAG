"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useState } from "react";
import type { ComponentType, ReactNode, SVGProps } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Dialog, DialogTitle, SheetContent } from "@acs/ui/components/dialog";
import { cn } from "@acs/ui/lib/utils";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import { useAuth } from "@/lib/auth/auth-context";
import { readStoredOrgId, resolveActiveOrgId } from "@/lib/orgs";

import {
  BookIcon,
  BotIcon,
  CardIcon,
  ChartIcon,
  ChatIcon,
  HomeIcon,
  LogOutIcon,
  MenuIcon,
  SettingsIcon,
  UsersIcon,
} from "./kit/icons";
import { ToastProvider } from "./kit/toast";
import { OrgSwitcher } from "./orgs/org-switcher";

interface NavItem {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  soon?: boolean;
}

export const NAV_SECTIONS: readonly { label: string; items: readonly NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      { href: "", label: "Overview", icon: HomeIcon },
      { href: "/chatbots", label: "Chatbots", icon: BotIcon },
      { href: "/knowledge", label: "Knowledge", icon: BookIcon },
      { href: "/conversations", label: "Conversations", icon: ChatIcon },
      { href: "/analytics", label: "Analytics", icon: ChartIcon },
    ],
  },
  {
    label: "Organization",
    items: [
      { href: "/members", label: "Team", icon: UsersIcon },
      { href: "/billing", label: "Billing", icon: CardIcon, soon: true },
      { href: "/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
];

/** Overview matches exactly; every other section also owns its sub-pages. */
export function isNavItemActive(pathname: string, orgBase: string, href: string): boolean {
  const target = `${orgBase}${href}`;
  if (href === "") return pathname === target;
  return pathname === target || pathname.startsWith(`${target}/`);
}

function VerifyEmailBanner() {
  const { refresh } = useAuth();
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function resend() {
    setStatus("sending");
    setError(null);
    try {
      await api.resendVerification();
      setStatus("sent");
    } catch (failure) {
      setError(describeApiError(failure));
      setStatus("idle");
    }
  }

  return (
    <Alert className="rounded-none border-x-0 border-t-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          {status === "sent"
            ? "Verification email sent. Check your inbox."
            : "Verify your email to create chatbots, invite teammates and create organizations."}
          {error && <span className="ml-2 text-destructive">{error}</span>}
        </span>
        <span className="flex gap-2">
          {status !== "sent" && (
            <Button
              size="sm"
              variant="outline"
              disabled={status === "sending"}
              onClick={() => void resend()}
            >
              {status === "sending" ? "Sending…" : "Resend verification email"}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => void refresh()}>
            I&apos;ve verified
          </Button>
        </span>
      </div>
    </Alert>
  );
}

function Brand() {
  return (
    <Link
      href="/dashboard"
      className="flex items-center gap-2 rounded-md font-semibold tracking-tight outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <span
        aria-hidden="true"
        className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-[inset_0_1px_0_oklch(1_0_0/0.25)]"
      >
        <BotIcon width={16} height={16} />
      </span>
      Support Platform
    </Link>
  );
}

function SidebarNav({
  orgBase,
  pathname,
  onNavigate,
}: {
  orgBase: string | null;
  pathname: string;
  onNavigate?: () => void;
}) {
  if (!orgBase) return null;
  return (
    <nav aria-label="Main" className="grid gap-6">
      {NAV_SECTIONS.map((section) => (
        <div key={section.label} className="grid gap-1">
          <p className="px-3 pb-1 text-xs font-medium tracking-wide text-muted-foreground">
            {section.label}
          </p>
          <ul className="grid gap-0.5">
            {section.items.map((item) => {
              const href = `${orgBase}${item.href}`;
              const active = isNavItemActive(pathname, orgBase, item.href);
              const Icon = item.icon;
              return (
                <li key={item.label}>
                  <Link
                    href={href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors outline-none hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      active &&
                        "bg-primary/90 font-medium text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground",
                    )}
                  >
                    <Icon />
                    <span className="flex-1">{item.label}</span>
                    {item.soon && (
                      <span className="rounded-full border border-current/30 px-1.5 text-[11px] leading-4 opacity-80">
                        Soon
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SidebarContent({
  orgs,
  activeOrgId,
  orgBase,
  pathname,
  userName,
  userEmail,
  onNavigate,
  onSignOut,
}: {
  orgs: readonly { id: string; name: string }[];
  activeOrgId: string | null;
  orgBase: string | null;
  pathname: string;
  userName: string;
  userEmail: string;
  onNavigate?: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="flex h-full flex-col gap-6 p-4">
      <Brand />
      <OrgSwitcher orgs={orgs} activeOrgId={activeOrgId} className="w-full" />
      <div className="flex-1 overflow-y-auto">
        <SidebarNav orgBase={orgBase} pathname={pathname} onNavigate={onNavigate} />
      </div>
      <div className="grid gap-2 border-t pt-4">
        <Link
          href="/account"
          onClick={onNavigate}
          aria-current={pathname === "/account" ? "page" : undefined}
          className="grid rounded-md px-3 py-2 text-sm outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <span className="truncate font-medium">{userName}</span>
          <span className="truncate text-xs text-muted-foreground">{userEmail}</span>
        </Link>
        <Button variant="ghost" size="sm" className="justify-start" onClick={onSignOut}>
          <LogOutIcon />
          Sign out
        </Button>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { state, signOut } = useAuth();
  const params = useParams<{ orgId?: string }>();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  if (state.status !== "authenticated") return null;

  const routeOrgId = params.orgId ?? null;
  // Outside an org route (account page, org creation) the nav points at the remembered org.
  const activeOrgId = resolveActiveOrgId(state.orgs, {
    routeOrgId,
    storedOrgId: routeOrgId ? null : readStoredOrgId(),
  });
  const orgBase = activeOrgId ? `/orgs/${encodeURIComponent(activeOrgId)}` : null;

  const sidebar = (onNavigate?: () => void) => (
    <SidebarContent
      orgs={state.orgs}
      activeOrgId={routeOrgId ? activeOrgId : null}
      orgBase={orgBase}
      pathname={pathname}
      userName={state.user.name}
      userEmail={state.user.email}
      onNavigate={onNavigate}
      onSignOut={() => void signOut()}
    />
  );

  return (
    <ToastProvider>
      <a
        href="#main-content"
        className="sr-only z-[70] rounded-md bg-background px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_1fr]">
        <aside className="theme-rail hidden lg:sticky lg:top-0 lg:block lg:h-dvh">
          {sidebar()}
        </aside>

        <div className="flex min-w-0 flex-col">
          <header className="theme-rail sticky top-0 z-40 flex items-center gap-3 px-4 py-2.5 lg:hidden">
            <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Open navigation"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen(true)}
              >
                <MenuIcon width={20} height={20} />
              </Button>
              <SheetContent aria-describedby={undefined} className="theme-rail">
                <DialogTitle className="sr-only">Navigation</DialogTitle>
                {sidebar(() => setMenuOpen(false))}
              </SheetContent>
            </Dialog>
            <Brand />
          </header>

          {!state.user.email_verified && <VerifyEmailBanner />}

          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8"
          >
            {children}
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
