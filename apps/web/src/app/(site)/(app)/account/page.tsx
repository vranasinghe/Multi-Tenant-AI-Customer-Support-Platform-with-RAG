import type { Metadata } from "next";

import { ChangePasswordForm, ProfileForm, SessionsList } from "@/components/account/account-panels";

export const metadata: Metadata = { title: "Account" };

export default function AccountPage() {
  return (
    <div className="grid gap-10">
      <h1 className="text-2xl font-semibold tracking-tight">Account</h1>
      <section aria-labelledby="profile-heading" className="grid gap-4">
        <h2 id="profile-heading" className="text-lg font-semibold">
          Profile
        </h2>
        <ProfileForm />
      </section>
      <section aria-labelledby="password-heading" className="grid gap-4">
        <h2 id="password-heading" className="text-lg font-semibold">
          Password
        </h2>
        <ChangePasswordForm />
      </section>
      <section aria-labelledby="sessions-heading" className="grid gap-4">
        <h2 id="sessions-heading" className="text-lg font-semibold">
          Devices
        </h2>
        <SessionsList />
      </section>
    </div>
  );
}
