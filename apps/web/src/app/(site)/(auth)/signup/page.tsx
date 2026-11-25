import type { Metadata } from "next";
import Link from "next/link";

import { AuthCard } from "@/components/auth/auth-card";
import { RedirectIfAuthenticated } from "@/components/auth/guards";
import { SignupForm } from "@/components/auth/signup-form";

export const metadata: Metadata = { title: "Create account" };

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const login = next ? `/login?next=${encodeURIComponent(next)}` : "/login";
  return (
    <AuthCard
      title="Create your account"
      description="You'll be the owner of the new organization."
      footer={
        <>
          Already have an account?{" "}
          <Link href={login} className="text-foreground underline underline-offset-4">
            Sign in
          </Link>
        </>
      }
    >
      <RedirectIfAuthenticated>
        <SignupForm next={next} />
      </RedirectIfAuthenticated>
    </AuthCard>
  );
}
