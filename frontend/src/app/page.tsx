"use client";

import { useEffect, useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  useThread,
  useThreadRuntime,
} from "@assistant-ui/react";
import { ragChatAdapter, setActiveLangCodes } from "@/lib/chatAdapter";
import type { ArtifactChunk, Claim } from "@/lib/types";
import { PdfViewer } from "@/components/PdfViewer";
import { UploadPdf } from "@/components/UploadPdf";

type CustomMeta = {
  answer_lang?: string;
  confidence?: number;
  attempts?: number;
  claims?: Claim[];
  artifact_chunks?: ArtifactChunk[];
};

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const cls = confidence >= 0.5 ? "confidence-high" : "confidence-low";
  return <span className={`confidence-badge ${cls}`}>confidence {pct}%</span>;
}

function Citations({
  chunks,
  claims,
  onSelect,
}: {
  chunks: ArtifactChunk[];
  claims: Claim[];
  onSelect: (chunk: ArtifactChunk) => void;
}) {
  const verifiedSources = new Set(chunks.map((c) => c.source));
  const unverified = claims.filter((c) => !c.verified);

  return (
    <div className="citations">
      {chunks.map((c, i) => (
        <button key={`${c.chunk_id}-${i}`} className="citation-item" onClick={() => onSelect(c)}>
          [{c.source}] {c.address.heading_path.join(" > ") || c.address.doc_id}
          {c.address.page != null ? ` · p.${c.address.page + 1}` : ""}
          <br />
          <em>&ldquo;{c.quote}&rdquo;</em>
        </button>
      ))}
      {unverified.map((c, i) => (
        <div key={`unverified-${i}`} className="citation-item unverified">
          [{c.source}] unverified — &ldquo;{c.quote}&rdquo;
        </div>
      ))}
      {chunks.length === 0 && unverified.length === 0 && verifiedSources.size === 0 && null}
    </div>
  );
}

function Thread({ onSelectChunk }: { onSelectChunk: (chunk: ArtifactChunk) => void }) {
  const messages = useThread((t) => t.messages);
  const isRunning = useThread((t) => t.isRunning);
  const runtime = useThreadRuntime();
  const [input, setInput] = useState("");
  const viewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    viewportRef.current?.scrollTo({ top: viewportRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function send() {
    const text = input.trim();
    if (!text || isRunning) return;
    runtime.append(text);
    setInput("");
  }

  return (
    <>
      <div className="thread-viewport" ref={viewportRef}>
        {messages.map((m) => {
          const text = m.content
            .filter((p): p is { type: "text"; text: string } => p.type === "text")
            .map((p) => p.text)
            .join("");
          const meta = (m.metadata?.custom ?? {}) as CustomMeta;

          return (
            <div key={m.id} className={`message-row ${m.role}`}>
              <div className="message-bubble">{text}</div>
              {m.role === "assistant" && meta.confidence !== undefined && (
                <ConfidenceBadge confidence={meta.confidence} />
              )}
              {m.role === "assistant" && (meta.artifact_chunks?.length || meta.claims?.length) && (
                <Citations
                  chunks={meta.artifact_chunks ?? []}
                  claims={meta.claims ?? []}
                  onSelect={onSelectChunk}
                />
              )}
            </div>
          );
        })}
        {isRunning && (
          <div className="message-row assistant">
            <div className="message-bubble">…</div>
          </div>
        )}
      </div>
      <div className="composer">
        <input
          value={input}
          placeholder="Frage stellen / Ask a question…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          disabled={isRunning}
        />
        <button onClick={send} disabled={isRunning || !input.trim()}>
          Senden
        </button>
      </div>
    </>
  );
}

export default function Home() {
  const runtime = useLocalRuntime(ragChatAdapter);
  const [selected, setSelected] = useState<ArtifactChunk | null>(null);
  const [jumpToken, setJumpToken] = useState(0);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg: { default_active_languages?: string[] }) => {
        if (cfg.default_active_languages) setActiveLangCodes(cfg.default_active_languages);
      })
      .catch(() => {});
  }, []);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div id="app-root">
        <div className="chat-pane">
          <div className="app-header">
            Local RAG — Document Assistant
            <UploadPdf />
          </div>
          <Thread
            onSelectChunk={(chunk) => {
              setSelected(chunk);
              setJumpToken((t) => t + 1);
            }}
          />
        </div>
        <div className="viewer-pane">
          <PdfViewer docId={selected?.address.doc_id ?? null} highlight={selected} jumpToken={jumpToken} />
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
}
