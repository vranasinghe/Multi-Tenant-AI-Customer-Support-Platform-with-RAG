"use client";

import { useId } from "react";

import { Badge } from "@acs/ui/components/badge";
import { Input } from "@acs/ui/components/input";
import { Label } from "@acs/ui/components/label";

import { RadioCards, SelectField, SwitchField, TextAreaField } from "@/components/form/fields";
import { TextField } from "@/components/form/text-field";
import type { ChatbotOptions } from "@/lib/api/types";
import { LENGTH_OPTIONS, LIMITS, TONE_OPTIONS } from "@/lib/chatbots";
import type { ChatbotForm, FormErrors } from "@/lib/chatbots";

export interface FieldsProps {
  form: ChatbotForm;
  errors: FormErrors;
  onChange: (patch: Partial<ChatbotForm>) => void;
  onWidgetChange: (patch: Partial<ChatbotForm["widget_settings"]>) => void;
  options: ChatbotOptions;
  disabled?: boolean;
}

const numberValue = (value: number) => (Number.isNaN(value) ? "" : String(value));
const parseNumber = (raw: string) => (raw.trim() === "" ? Number.NaN : Number(raw));

export function BasicsFields({ form, errors, onChange, disabled }: FieldsProps) {
  return (
    <div className="grid gap-5">
      <TextField
        label="Name"
        name="name"
        value={form.name}
        maxLength={LIMITS.name + 20}
        error={errors.name}
        hint="Shown to visitors as the chat title."
        disabled={disabled}
        onChange={(event) => onChange({ name: event.target.value })}
      />
      <TextAreaField
        label="Description"
        name="description"
        rows={2}
        value={form.description}
        maxLength={LIMITS.description}
        error={errors.description}
        hint="Internal note for your team. Visitors never see it."
        disabled={disabled}
        onChange={(event) => onChange({ description: event.target.value })}
      />
      <TextAreaField
        label="Welcome message"
        name="welcome_message"
        rows={2}
        value={form.welcome_message}
        maxLength={LIMITS.message}
        error={errors.welcome_message}
        hint="The first message visitors see when they open the chat."
        disabled={disabled}
        onChange={(event) => onChange({ welcome_message: event.target.value })}
      />
    </div>
  );
}

export function BehaviorFields({ form, errors, onChange, disabled }: FieldsProps) {
  return (
    <div className="grid gap-6">
      <TextAreaField
        label="System instructions"
        name="instructions"
        rows={7}
        value={form.instructions}
        maxLength={LIMITS.instructions}
        error={errors.instructions}
        placeholder="e.g. You help customers of Acme with orders, shipping and returns. Never discuss pricing exceptions."
        hint="What the assistant does, what it must avoid, and how to escalate."
        disabled={disabled}
        onChange={(event) => onChange({ instructions: event.target.value })}
      />
      <RadioCards
        legend="Tone"
        name="tone"
        value={form.tone}
        options={TONE_OPTIONS}
        disabled={disabled}
        onChange={(tone) => onChange({ tone })}
      />
      <RadioCards
        legend="Response length"
        name="response_length"
        value={form.response_length}
        options={LENGTH_OPTIONS}
        columns={3}
        disabled={disabled}
        onChange={(response_length) => onChange({ response_length })}
      />
      <TextAreaField
        label="Fallback message"
        name="fallback_message"
        rows={2}
        value={form.fallback_message}
        maxLength={LIMITS.message}
        error={errors.fallback_message}
        hint="Sent when the knowledge base has no confident answer."
        disabled={disabled}
        onChange={(event) => onChange({ fallback_message: event.target.value })}
      />
      <div className="grid gap-3">
        <SwitchField
          label="Answer only from your knowledge"
          hint="Recommended. When off, the assistant may use general knowledge for unrelated questions."
          checked={form.strict_grounding}
          disabled={disabled}
          onCheckedChange={(strict_grounding) => onChange({ strict_grounding })}
        />
        <SwitchField
          label="Show sources"
          hint="Add links to the documents an answer was based on."
          checked={form.show_sources}
          disabled={disabled}
          onCheckedChange={(show_sources) => onChange({ show_sources })}
        />
      </div>
    </div>
  );
}

export function LanguageFields({ form, errors, onChange, options, disabled }: FieldsProps) {
  return (
    <div className="grid gap-5">
      <RadioCards
        legend="Reply language"
        name="language_mode"
        value={form.language_mode}
        disabled={disabled}
        options={[
          {
            value: "auto",
            label: "Match the visitor",
            description: "Reply in the language each visitor writes in.",
          },
          {
            value: "fixed",
            label: "Always one language",
            description: "Reply in a single language you choose.",
          },
        ]}
        onChange={(language_mode) => onChange({ language_mode })}
      />
      {form.language_mode === "fixed" && (
        <SelectField
          label="Language"
          name="language"
          value={form.language}
          error={errors.language}
          disabled={disabled}
          onChange={(event) => onChange({ language: event.target.value })}
        >
          <option value="">Choose a language…</option>
          {options.languages.map((language) => (
            <option key={language.code} value={language.code}>
              {language.label}
            </option>
          ))}
        </SelectField>
      )}
    </div>
  );
}

function ColorField({
  label,
  value,
  error,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  error?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const id = useId();
  const errorId = `${id}-error`;
  const valid = /^#[0-9A-Fa-f]{6}$/.test(value);
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} picker`}
          value={valid ? value.toLowerCase() : "#000000"}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="h-9 w-11 shrink-0 cursor-pointer rounded-md border bg-transparent p-1 disabled:cursor-not-allowed"
        />
        <Input
          id={id}
          value={value}
          maxLength={7}
          spellCheck={false}
          autoComplete="off"
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className="font-mono uppercase"
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {error && (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export function AppearanceFields({ form, errors, onWidgetChange, disabled }: FieldsProps) {
  const widget = form.widget_settings;
  return (
    <div className="grid gap-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <ColorField
          label="Brand color"
          value={widget.primary_color}
          error={errors["widget_settings.primary_color"]}
          disabled={disabled}
          onChange={(primary_color) => onWidgetChange({ primary_color })}
        />
        <ColorField
          label="Background color"
          value={widget.accent_color}
          error={errors["widget_settings.accent_color"]}
          disabled={disabled}
          onChange={(accent_color) => onWidgetChange({ accent_color })}
        />
      </div>
      <TextField
        label="Avatar image URL"
        name="avatar_url"
        type="url"
        inputMode="url"
        placeholder="https://example.com/avatar.png"
        value={widget.avatar_url}
        error={errors["widget_settings.avatar_url"]}
        hint="Optional. A square https:// image. Without one, the bot's initials are shown."
        disabled={disabled}
        onChange={(event) => onWidgetChange({ avatar_url: event.target.value })}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Launcher label"
          name="launcher_label"
          value={widget.launcher_label}
          maxLength={LIMITS.launcherLabel + 10}
          error={errors["widget_settings.launcher_label"]}
          disabled={disabled}
          onChange={(event) => onWidgetChange({ launcher_label: event.target.value })}
        />
        <SelectField
          label="Position on page"
          name="position"
          value={widget.position}
          disabled={disabled}
          onChange={(event) =>
            onWidgetChange({
              position: event.target.value === "bottom-left" ? "bottom-left" : "bottom-right",
            })
          }
        >
          <option value="bottom-right">Bottom right</option>
          <option value="bottom-left">Bottom left</option>
        </SelectField>
      </div>
      <SwitchField
        label="Show “Powered by” badge"
        checked={widget.show_branding}
        disabled={disabled}
        onCheckedChange={(show_branding) => onWidgetChange({ show_branding })}
      />
    </div>
  );
}

export function ModelFields({ form, errors, onChange, options, disabled }: FieldsProps) {
  const selected = options.models.find((m) => m.id === form.model);
  return (
    <div className="grid gap-6">
      <RadioCards
        legend="Model"
        name="model"
        value={form.model}
        columns={3}
        disabled={disabled}
        error={errors.model}
        options={options.models.map((model) => ({
          value: model.id,
          label: model.label,
          description: model.description,
          badge: model.default ? (
            <Badge variant="secondary">Default</Badge>
          ) : model.tier === "advanced" ? (
            <Badge variant="outline">Advanced</Badge>
          ) : undefined,
        }))}
        onChange={(model) => onChange({ model })}
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField
          label="Temperature"
          name="temperature"
          type="number"
          inputMode="decimal"
          min={0}
          max={1}
          step={0.05}
          value={numberValue(form.temperature)}
          error={errors.temperature}
          hint="0 = consistent, 1 = varied."
          disabled={disabled}
          onChange={(event) => onChange({ temperature: parseNumber(event.target.value) })}
        />
        <TextField
          label="Max response tokens"
          name="max_output_tokens"
          type="number"
          inputMode="numeric"
          min={LIMITS.minTokens}
          max={selected?.max_output_tokens ?? LIMITS.maxTokens}
          step={1}
          value={numberValue(form.max_output_tokens)}
          error={errors.max_output_tokens}
          hint={`Up to ${selected?.max_output_tokens ?? LIMITS.maxTokens} for this model.`}
          disabled={disabled}
          onChange={(event) => onChange({ max_output_tokens: parseNumber(event.target.value) })}
        />
        <TextField
          label="Sources per answer"
          name="retrieval_top_k"
          type="number"
          inputMode="numeric"
          min={LIMITS.minTopK}
          max={LIMITS.maxTopK}
          step={1}
          value={numberValue(form.retrieval_top_k)}
          error={errors.retrieval_top_k}
          hint={`Knowledge passages retrieved (${LIMITS.minTopK}–${LIMITS.maxTopK}).`}
          disabled={disabled}
          onChange={(event) => onChange({ retrieval_top_k: parseNumber(event.target.value) })}
        />
      </div>
    </div>
  );
}
