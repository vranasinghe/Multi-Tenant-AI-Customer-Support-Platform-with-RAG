import type { Metadata } from "next";
import Link from "next/link";

import { AuthCard } from "@/components/auth/auth-card";
import { RedirectIfAuthenticated } from "@/components/auth/guards";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const signup = next ? `/signup?next=${encodeURIComponent(next)}` : "/signup";
  return (
    <AuthCard
      title="Sign in"
      footer={
        <>
          New here?{" "}
          <Link href={signup} className="text-foreground underline underline-offset-4">
            Create an account
          </Link>
        </>
      }
    >
      <RedirectIfAuthenticated>
        <LoginForm next={next} />
      </RedirectIfAuthenticated>
    </AuthCard>
  );
}
