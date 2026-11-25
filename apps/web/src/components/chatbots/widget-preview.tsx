"use client";

import { useState } from "react";

import { cn } from "@acs/ui/lib/utils";

import { contrastText, initials } from "@/lib/chatbots";
import type { ChatbotForm } from "@/lib/chatbots";

import { ChatIcon } from "../kit/icons";

const HEX = /^#[0-9A-Fa-f]{6}$/;

export function BotAvatar({
  name,
  avatarUrl,
  color,
  size = "md",
}: {
  name: string;
  avatarUrl: string | null;
  color: string;
  size?: "sm" | "md";
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const background = HEX.test(color) ? color : "#4F46E5";
  const dimension = size === "sm" ? "size-8 text-xs" : "size-10 text-sm";
  const showImage = avatarUrl && /^https:\/\//i.test(avatarUrl) && failedUrl !== avatarUrl;
  return showImage ? (
    // eslint-disable-next-line @next/next/no-img-element -- arbitrary customer-hosted URL
    <img
      src={avatarUrl}
      alt=""
      referrerPolicy="no-referrer"
      onError={() => setFailedUrl(avatarUrl)}
      className={cn("shrink-0 rounded-full object-cover", dimension)}
    />
  ) : (
    <span
      aria-hidden="true"
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold",
        dimension,
      )}
      style={{ background, color: contrastText(background) }}
    >
      {initials(name || "Bot")}
    </span>
  );
}

/**
 * Static preview of the chat widget with the current (unsaved) settings. It is a visual aid
 * only; the real widget ships with the embeddable widget phase.
 */
export function WidgetPreview({ form }: { form: ChatbotForm }) {
  const widget = form.widget_settings;
  const primary = HEX.test(widget.primary_color) ? widget.primary_color : "#4F46E5";
  const surface = HEX.test(widget.accent_color) ? widget.accent_color : "#FFFFFF";
  const onPrimary = contrastText(primary);
  const onSurface = contrastText(surface);
  const name = form.name.trim() || "Your assistant";
  const left = widget.position === "bottom-left";

  return (
    <figure className="grid gap-2" aria-label="Widget preview">
      <div className="relative overflow-hidden rounded-xl border bg-[repeating-linear-gradient(45deg,var(--muted),var(--muted)_10px,transparent_10px,transparent_20px)] p-4">
        <div className={cn("flex flex-col gap-3", left ? "items-start" : "items-end")}>
          <div
            className="flex w-full max-w-72 flex-col overflow-hidden rounded-2xl border shadow-lg"
            style={{ background: surface, color: onSurface }}
          >
            <div
              className="flex items-center gap-3 px-4 py-3"
              style={{ background: primary, color: onPrimary }}
            >
              <BotAvatar
                name={name}
                avatarUrl={widget.avatar_url.trim() || null}
                color={onPrimary === "#FFFFFF" ? "#FFFFFF33" : "#00000022"}
                size="sm"
              />
              <span className="truncate text-sm font-semibold">{name}</span>
            </div>
            <div className="grid gap-2 px-4 py-4 text-sm">
              <p
                className="max-w-[85%] rounded-2xl rounded-tl-sm px-3 py-2"
                style={{ background: `${onSurface}0F` }}
              >
                {form.welcome_message.trim() || "Hi! How can I help you today?"}
              </p>
            </div>
            <div
              className="border-t px-4 py-3 text-xs opacity-60"
              style={{ borderColor: `${onSurface}1A` }}
            >
              Type your question…
            </div>
            {widget.show_branding && (
              <p className="pb-2 text-center text-[11px] opacity-50">Powered by Support Platform</p>
            )}
          </div>
          <span
            className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium shadow-md"
            style={{ background: primary, color: onPrimary }}
          >
            <ChatIcon />
            {widget.launcher_label.trim() || "Chat with us"}
          </span>
        </div>
      </div>
      <figcaption className="text-xs text-muted-foreground">
        Preview only. The embeddable widget ships in a later phase.
      </figcaption>
    </figure>
  );
}
