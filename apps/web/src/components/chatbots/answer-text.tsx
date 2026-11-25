import type { ReactNode } from "react";

/**
 * Renders a chatbot answer. Models reply in light markdown (bold, lists, [n] source markers);
 * showing the raw symbols looks broken. This builds React elements only — never HTML strings —
 * so model or document text can't inject markup.
 */

const INLINE = /(\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*|`[^`\n]+`|\[\d{1,2}\])/g;

function inline(text: string, keyPrefix: string): ReactNode[] {
  return text
    .replace(/[ \t]+(\[\d{1,2}\])/g, "$1")
    .split(INLINE)
    .map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={key} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={key} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    if (/^\[\d{1,2}\]$/.test(part)) {
      return (
        <sup
          key={key}
          aria-label={`source ${part.slice(1, -1)}`}
          className="mx-0.5 inline-flex min-w-4 items-center justify-center rounded bg-accent px-1 text-[0.68rem] leading-4 font-semibold text-accent-foreground"
        >
          {part.slice(1, -1)}
        </sup>
      );
    }
    return part;
  });
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul" | "ol"; items: string[] };

function parse(text: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const ordered = /^\s*\d{1,2}[.)]\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const last = blocks.at(-1);
    if (line.trim() === "") {
      blocks.push({ kind: "p", lines: [] });
    } else if (ordered || bullet) {
      const kind = ordered ? "ol" : "ul";
      const item = (ordered ?? bullet)![1] ?? "";
      if (last?.kind === kind) last.items.push(item);
      else blocks.push({ kind, items: [item] });
    } else if (last?.kind === "p") {
      last.lines.push(line.trim());
    } else {
      blocks.push({ kind: "p", lines: [line.trim()] });
    }
  }
  return blocks.filter((b) => (b.kind === "p" ? b.lines.length > 0 : true));
}

export function AnswerText({ text }: { text: string }) {
  const blocks = parse(text);
  return (
    <div className="grid max-w-prose gap-3 text-[0.9375rem] leading-relaxed break-words">
      {blocks.map((block, i) => {
        if (block.kind === "p") {
          return <p key={i}>{inline(block.lines.join(" "), `p${i}`)}</p>;
        }
        const List = block.kind === "ol" ? "ol" : "ul";
        return (
          <List
            key={i}
            className={`grid gap-1.5 pl-5 marker:text-muted-foreground ${block.kind === "ol" ? "list-decimal" : "list-disc"}`}
          >
            {block.items.map((item, j) => (
              <li key={j} className="pl-1">
                {inline(item, `l${i}-${j}`)}
              </li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
