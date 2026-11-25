"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { SessionInfo } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { useAsyncData } from "@/lib/use-async-data";
import {
  changePasswordSchema,
  fieldErrorsFromZod,
  PASSWORD_MIN,
  profileSchema,
} from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

import { TextField, useFocusFirstInvalid } from "../form/text-field";

export function ProfileForm() {
  const { state, refresh } = useAuth();
  const [name, setName] = useState(state.status === "authenticated" ? state.user.name : "");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setMessage(null);
    const parsed = profileSchema.safeParse({ name });
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});
    setPending(true);
    try {
      await api.updateMe({ name: parsed.data.name });
      await refresh();
      setMessage({ kind: "ok", text: "Saved." });
    } catch (error) {
      setMessage({ kind: "error", text: describeApiError(error) });
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid max-w-sm gap-4">
      {message && (
        <Alert variant={message.kind === "ok" ? "success" : "destructive"}>{message.text}</Alert>
      )}
      <TextField
        label="Your name"
        name="name"
        autoComplete="name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={errors.name}
      />
      <TextField
        label="Email"
        type="email"
        value={state.status === "authenticated" ? state.user.email : ""}
        readOnly
        disabled
        hint="Contact support to change your email address."
      />
      <Button type="submit" disabled={pending} className="justify-self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}

export function ChangePasswordForm() {
  const formRef = useRef<HTMLFormElement>(null);
  const [values, setValues] = useState({ currentPassword: "", newPassword: "", confirm: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [pending, setPending] = useState(false);

  useFocusFirstInvalid(formRef, errors);

  const set = (key: keyof typeof values) => (event: { target: { value: string } }) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setMessage(null);
    const parsed = changePasswordSchema.safeParse(values);
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});
    setPending(true);
    try {
      await api.changePassword({
        current_password: parsed.data.currentPassword,
        new_password: parsed.data.newPassword,
      });
      setValues({ currentPassword: "", newPassword: "", confirm: "" });
      setMessage({ kind: "ok", text: "Password changed. Other devices were signed out." });
    } catch (error) {
      if (error instanceof ApiError && error.fieldErrors.new_password) {
        setErrors({ newPassword: error.fieldErrors.new_password });
      } else if (error instanceof ApiError && error.code === "invalid_credentials") {
        setErrors({ currentPassword: "That isn't your current password." });
      } else {
        setMessage({ kind: "error", text: describeApiError(error) });
      }
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
        label="Current password"
        type="password"
        autoComplete="current-password"
        value={values.currentPassword}
        onChange={set("currentPassword")}
        error={errors.currentPassword}
      />
      <TextField
        label="New password"
        type="password"
        autoComplete="new-password"
        value={values.newPassword}
        onChange={set("newPassword")}
        error={errors.newPassword}
        hint={`At least ${PASSWORD_MIN} characters.`}
      />
      <TextField
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        value={values.confirm}
        onChange={set("confirm")}
        error={errors.confirm}
      />
      <Button type="submit" disabled={pending} className="justify-self-start">
        {pending ? "Changing…" : "Change password"}
      </Button>
    </form>
  );
}

export function SessionsList() {
  const {
    data,
    error: loadError,
    reload,
  } = useAsyncData(async () => (await api.listSessions()).data, []);
  const [actionError, setActionError] = useState<string | null>(null);
  const sessions: SessionInfo[] | null = data;
  const error = actionError ?? loadError;

  async function revoke(id: string) {
    setActionError(null);
    try {
      await api.revokeSession(id);
      reload();
    } catch (failure) {
      setActionError(describeApiError(failure));
    }
  }

  async function revokeOthers() {
    setActionError(null);
    try {
      await api.revokeOtherSessions();
      reload();
    } catch (failure) {
      setActionError(describeApiError(failure));
    }
  }

  if (sessions === null) {
    return error ? (
      <Alert variant="destructive">{error}</Alert>
    ) : (
      <p className="text-sm text-muted-foreground">Loading sessions…</p>
    );
  }
  const others = sessions.filter((s) => !s.current).length;
  return (
    <div className="grid gap-3">
      {error && <Alert variant="destructive">{error}</Alert>}
      <ul className="divide-y rounded-md border text-sm">
        {sessions.map((session) => (
          <li
            key={session.id}
            className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
          >
            <div>
              <div className="font-medium">
                {session.current ? "This device" : (session.user_agent ?? "Unknown device")}
              </div>
              <div className="text-muted-foreground">
                Last active{" "}
                <time dateTime={session.last_seen_at}>
                  {new Date(session.last_seen_at).toLocaleString()}
                </time>
              </div>
            </div>
            {!session.current && (
              <Button size="sm" variant="outline" onClick={() => void revoke(session.id)}>
                Sign out
              </Button>
            )}
          </li>
        ))}
      </ul>
      {others > 0 && (
        <Button
          variant="outline"
          className="justify-self-start"
          onClick={() => void revokeOthers()}
        >
          Sign out all other devices
        </Button>
      )}
    </div>
  );
}
