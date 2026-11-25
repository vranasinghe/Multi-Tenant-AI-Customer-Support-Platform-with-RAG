"use client";

import { useId, useRef, useState } from "react";
import type { ReactNode } from "react";

import { Button } from "@acs/ui/components/button";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@acs/ui/components/dialog";
import { Input } from "@acs/ui/components/input";
import { Label } from "@acs/ui/components/label";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  /** Runs the action. The dialog stays open (buttons disabled) until it settles. */
  onConfirm: () => Promise<void> | void;
  destructive?: boolean;
  /** When set, the user must type this exact text before confirming (high-impact actions). */
  confirmText?: string;
}

/**
 * Confirmation for destructive or irreversible actions. Built on AlertDialog: focus is trapped,
 * Cancel is focused first, Escape cancels, and focus returns to the trigger on close.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = false,
  confirmText,
}: ConfirmDialogProps) {
  const inputId = useId();
  // The dialog is opened from state, not a Radix trigger, so remember the opener ourselves and
  // return focus to it on close (skipped automatically if it was removed, e.g. after a delete).
  const opener = useRef<HTMLElement | null>(null);
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);
  const matches = !confirmText || typed.trim() === confirmText;

  async function confirm() {
    if (!matches || pending) return;
    setPending(true);
    try {
      await onConfirm();
    } finally {
      setPending(false);
      setTyped("");
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        if (!next) setTyped("");
        onOpenChange(next);
      }}
    >
      <AlertDialogContent
        onOpenAutoFocus={() => {
          opener.current = document.activeElement as HTMLElement | null;
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          if (opener.current?.isConnected) opener.current.focus();
        }}
      >
        <div className="grid gap-2">
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>{description}</div>
          </AlertDialogDescription>
        </div>
        {confirmText && (
          <div className="grid gap-1.5">
            <Label htmlFor={inputId}>
              Type <strong className="font-semibold">{confirmText}</strong> to confirm
            </Label>
            <Input
              id={inputId}
              value={typed}
              autoComplete="off"
              onChange={(event) => setTyped(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void confirm();
                }
              }}
            />
          </div>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <AlertDialogCancel asChild>
            <Button variant="outline" disabled={pending}>
              Cancel
            </Button>
          </AlertDialogCancel>
          {/* Not AlertDialogAction: that would close the dialog before the action finishes. */}
          <Button
            variant={destructive ? "destructive" : "default"}
            disabled={!matches || pending}
            onClick={() => void confirm()}
          >
            {pending ? "Working…" : confirmLabel}
          </Button>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
