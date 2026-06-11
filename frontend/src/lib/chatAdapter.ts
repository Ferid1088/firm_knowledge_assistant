import type { ChatModelAdapter, ChatModelRunOptions, ChatModelRunResult } from "@assistant-ui/react";
import type { ChatResponse } from "./types";

// Active languages selectable in the UI dropdown (German always-on per CLAUDE.md;
// fetched from /api/config so the registry stays the single source of truth).
let activeLangCodes: string[] = ["de", "en"];

export function setActiveLangCodes(codes: string[]) {
  activeLangCodes = codes;
}

export const ragChatAdapter: ChatModelAdapter = {
  async run({ messages, abortSignal }: ChatModelRunOptions): Promise<ChatModelRunResult> {
    const last = messages[messages.length - 1];
    const question = last.content
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("\n");

    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, active_lang_codes: activeLangCodes }),
      signal: abortSignal,
    });

    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`API error ${res.status}: ${detail}`);
    }

    const data: ChatResponse = await res.json();

    return {
      content: [{ type: "text", text: data.answer }],
      status: { type: "complete", reason: "stop" },
      metadata: {
        custom: {
          answer_lang: data.answer_lang,
          confidence: data.confidence,
          attempts: data.attempts,
          supporting_points: data.supporting_points,
          caveats: data.caveats,
          claims: data.claims,
          artifact_chunks: data.artifact_chunks,
        },
      },
    };
  },
};
