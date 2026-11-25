"use client";

import { useId } from "react";
import type { ComponentProps, ReactNode } from "react";

import { Label } from "@acs/ui/components/label";
import { Select } from "@acs/ui/components/select";
import { Switch } from "@acs/ui/components/switch";
import { Textarea } from "@acs/ui/components/textarea";
import { cn } from "@acs/ui/lib/utils";

interface FieldMeta {
  label: string;
  error?: string;
  hint?: ReactNode;
}

/** Shared label/hint/error wiring so every control is announced the same way. */
function useFieldIds(hint: ReactNode, error: string | undefined) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  return { id, hintId, errorId, describedBy: describedBy || undefined };
}

function FieldMessages({
  hint,
  hintId,
  error,
  errorId,
}: {
  hint?: ReactNode;
  hintId: string;
  error?: string;
  errorId: string;
}) {
  return (
    <>
      {hint && (
        <p id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </>
  );
}

export function TextAreaField({
  label,
  error,
  hint,
  maxLength,
  value,
  ...props
}: FieldMeta & Omit<ComponentProps<"textarea">, "id"> & { value: string }) {
  const ids = useFieldIds(hint, error);
  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={ids.id}>{label}</Label>
        {maxLength && (
          <span
            className={cn(
              "text-xs text-muted-foreground tabular-nums",
              value.length > maxLength && "text-destructive",
            )}
            aria-hidden="true"
          >
            {value.length}/{maxLength}
          </span>
        )}
      </div>
      <Textarea
        id={ids.id}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={ids.describedBy}
        {...props}
      />
      <FieldMessages hint={hint} hintId={ids.hintId} error={error} errorId={ids.errorId} />
    </div>
  );
}

export function SelectField({
  label,
  error,
  hint,
  children,
  ...props
}: FieldMeta & Omit<ComponentProps<"select">, "id">) {
  const ids = useFieldIds(hint, error);
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={ids.id}>{label}</Label>
      <Select
        id={ids.id}
        aria-invalid={error ? true : undefined}
        aria-describedby={ids.describedBy}
        {...props}
      >
        {children}
      </Select>
      <FieldMessages hint={hint} hintId={ids.hintId} error={error} errorId={ids.errorId} />
    </div>
  );
}

export function SwitchField({
  label,
  hint,
  checked,
  onCheckedChange,
  disabled,
  name,
}: {
  label: string;
  hint?: ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  name?: string;
}) {
  const ids = useFieldIds(hint, undefined);
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
      <div className="grid gap-1">
        <Label htmlFor={ids.id}>{label}</Label>
        {hint && (
          <p id={ids.hintId} className="text-sm text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
      <Switch
        id={ids.id}
        name={name}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-describedby={ids.describedBy}
      />
    </div>
  );
}

/** A group of mutually exclusive cards (native radios: arrow keys move the selection). */
export function RadioCards<T extends string>({
  legend,
  name,
  value,
  onChange,
  options,
  disabled,
  error,
  columns = 2,
}: {
  legend: string;
  name: string;
  value: T;
  onChange: (value: T) => void;
  options: readonly { value: T; label: string; description?: ReactNode; badge?: ReactNode }[];
  disabled?: boolean;
  error?: string;
  columns?: 2 | 3;
}) {
  const errorId = useId();
  return (
    <fieldset
      className="grid gap-2"
      aria-describedby={error ? errorId : undefined}
      disabled={disabled}
    >
      <legend className="mb-1.5 text-sm font-medium">{legend}</legend>
      <div
        className={cn(
          "grid gap-2",
          columns === 3 ? "sm:grid-cols-2 xl:grid-cols-3" : "sm:grid-cols-2",
        )}
      >
        {options.map((option) => (
          <label
            key={option.value}
            className={cn(
              "relative flex cursor-pointer flex-col gap-1 rounded-lg border p-3 text-sm transition-colors hover:bg-accent/60",
              "has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50",
              "has-[:checked]:border-foreground has-[:checked]:bg-accent/40",
              "has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            <span className="flex items-center justify-between gap-2 font-medium">
              {option.label}
              {option.badge}
            </span>
            {option.description && (
              <span className="text-muted-foreground">{option.description}</span>
            )}
          </label>
        ))}
      </div>
      {error && (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </fieldset>
  );
}
