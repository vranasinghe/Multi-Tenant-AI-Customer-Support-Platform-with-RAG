import { describe, expect, it } from "vitest";

import { OPTIONS, chatbot } from "@/test/fixtures";

import {
  DEFAULT_FORM,
  contrastText,
  diffForUpdate,
  errorsFromApi,
  formFromChatbot,
  initials,
  toCreateBody,
  validateFields,
} from "./chatbots";

const valid = { ...DEFAULT_FORM, name: "Helper" };

describe("validateFields", () => {
  it("accepts the defaults once a name is set", () => {
    expect(validateFields(valid, OPTIONS.models)).toEqual({});
  });

  it("requires a non-blank name and enforces length limits", () => {
    expect(validateFields({ ...valid, name: "   " }, OPTIONS.models)).toHaveProperty("name");
    expect(validateFields({ ...valid, name: "x".repeat(81) }, OPTIONS.models)).toHaveProperty(
      "name",
    );
    expect(
      validateFields({ ...valid, instructions: "x".repeat(4001) }, OPTIONS.models),
    ).toHaveProperty("instructions");
  });

  it("rejects control characters", () => {
    expect(validateFields({ ...valid, name: "bad\u0000" }, OPTIONS.models)).toHaveProperty("name");
  });

  it("requires a language when the language is fixed", () => {
    const errors = validateFields({ ...valid, language_mode: "fixed" }, OPTIONS.models);
    expect(errors.language).toBe("Choose a language.");
  });

  it("checks token limits against the selected model", () => {
    const errors = validateFields(
      { ...valid, model: "gpt-4.1-nano", max_output_tokens: 3000 },
      OPTIONS.models,
    );
    expect(errors.max_output_tokens).toMatch(/at most 2048/);
  });

  it("validates nested widget settings with dotted keys", () => {
    const errors = validateFields(
      {
        ...valid,
        widget_settings: {
          ...valid.widget_settings,
          primary_color: "blue",
          avatar_url: "http://insecure.example/a.png",
        },
      },
      OPTIONS.models,
    );
    expect(Object.keys(errors).sort()).toEqual([
      "widget_settings.avatar_url",
      "widget_settings.primary_color",
    ]);
  });

  it("treats an emptied number input (NaN) as invalid", () => {
    expect(validateFields({ ...valid, temperature: Number.NaN }, OPTIONS.models)).toHaveProperty(
      "temperature",
    );
  });

  it("limits results to the requested fields, including nested groups", () => {
    const form = {
      ...valid,
      name: "",
      widget_settings: { ...valid.widget_settings, accent_color: "nope" },
    };
    expect(Object.keys(validateFields(form, OPTIONS.models, ["name"]))).toEqual(["name"]);
    expect(Object.keys(validateFields(form, OPTIONS.models, ["widget_settings"]))).toEqual([
      "widget_settings.accent_color",
    ]);
  });
});

describe("request bodies", () => {
  it("trims text, nulls empty avatar and drops the language in auto mode", () => {
    const body = toCreateBody(
      { ...valid, name: "  Helper  ", language: "fr", language_mode: "auto" },
      "draft",
    );
    expect(body.name).toBe("Helper");
    expect(body.language).toBeNull();
    expect(body.widget_settings?.avatar_url).toBeNull();
    expect(body.status).toBe("draft");
  });

  it("sends only changed fields in an update", () => {
    const bot = chatbot();
    const form = formFromChatbot(bot);
    expect(diffForUpdate(bot, form)).toEqual({});

    const edited = {
      ...form,
      description: "New",
      widget_settings: { ...form.widget_settings, primary_color: "#112233" },
    };
    expect(diffForUpdate(bot, edited)).toEqual({
      description: "New",
      widget_settings: { primary_color: "#112233" },
    });
  });

  it("normalizes color case so retyping the same color is not a change", () => {
    const bot = chatbot();
    const form = formFromChatbot(bot);
    const same = {
      ...form,
      widget_settings: { ...form.widget_settings, primary_color: "#4f46e5" },
    };
    expect(diffForUpdate(bot, same)).toEqual({});
  });

  it("maps API field errors to form keys", () => {
    expect(errorsFromApi({ "widget_settings.primary_color": "bad", name: "taken" })).toEqual({
      "widget_settings.primary_color": "bad",
      name: "taken",
    });
  });
});

describe("display helpers", () => {
  it("picks readable text on brand colors", () => {
    expect(contrastText("#FFFFFF")).toBe("#000000");
    expect(contrastText("#111827")).toBe("#FFFFFF");
    expect(contrastText("not-a-color")).toBe("#FFFFFF");
  });

  it("derives initials", () => {
    expect(initials("Support Bot")).toBe("SB");
    expect(initials("acme")).toBe("A");
    expect(initials("")).toBe("?");
  });
});
