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
  supporting_points?: string[];
  caveats?: string[];
  claims?: Claim[];
  artifact_chunks?: ArtifactChunk[];
};

// ── Icons (inline SVG, no external/CDN icon set per air-gap rules) ────────

function DocumentIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

function BookOpenIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M2 4h6a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z" />
      <path d="M22 4h-6a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h7z" />
    </svg>
  );
}

function CheckCircleIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <path d="m9 11 3 3L22 4" />
    </svg>
  );
}

function AlertTriangleIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

function QuoteIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M9.5 7C6.5 7 4 9.5 4 12.5S6.5 18 9.5 18c.3 0 .5-.2.5-.5s-.2-.5-.5-.5C7.6 17 6 15.4 6 13.5V13h2.5c.8 0 1.5-.7 1.5-1.5v-3C10 7.7 9.3 7 8.5 7zM18.5 7c-3 0-5.5 2.5-5.5 5.5S15.5 18 18.5 18c.3 0 .5-.2.5-.5s-.2-.5-.5-.5c-1.9 0-3.5-1.6-3.5-3.5V13h2.5c.8 0 1.5-.7 1.5-1.5v-3c0-.8-.7-1.5-1.5-1.5z" />
    </svg>
  );
}

function SparkleIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
    </svg>
  );
}

function InfoIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4M12 8h.01" />
    </svg>
  );
}

function SendIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}

function MessageIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

// ── Small presentational components ───────────────────────────────────────

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const cls = confidence >= 0.5 ? "confidence-high" : "confidence-low";
  return (
    <span className={`confidence-badge ${cls}`}>
      <span className="dot" aria-hidden="true" />
      Confidence {pct}%
    </span>
  );
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
  const unverified = claims.filter((c) => !c.verified);
  const extraUnverified = unverified.filter(
    (c) => !chunks.some((chunk) => chunk.source === c.source)
  );

  if (chunks.length === 0 && extraUnverified.length === 0) return null;

  return (
    <div className="citations">
      <div className="citations-title">
        <BookOpenIcon aria-hidden="true" />
        References
      </div>
      {chunks.map((c, i) => {
        const isVerified = c.verified !== false;
        const path = c.address.heading_path.join(" › ") || c.address.doc_id;
        return (
          <button
            key={`${c.chunk_id}-${i}`}
            type="button"
            className={`citation-item ${isVerified ? "" : "unverified"}`.trim()}
            onClick={() => onSelect(c)}
            title={`${c.address.doc_id}${c.address.page != null ? ` · page ${c.address.page + 1}` : ""}`}
          >
            <div className="citation-head">
              <div className="citation-meta">
                <span className="citation-number" aria-hidden="true">
                  {c.source}
                </span>
                <span className="citation-path">{path}</span>
                {c.address.page != null && (
                  <span className="citation-page">p. {c.address.page + 1}</span>
                )}
              </div>
              {isVerified ? (
                <span className="citation-status verified">
                  <CheckCircleIcon aria-hidden="true" />
                  Verified
                </span>
              ) : (
                <span className="citation-status unverified">
                  <AlertTriangleIcon aria-hidden="true" />
                  Unverified
                </span>
              )}
            </div>
            <div className="citation-quote">
              <QuoteIcon aria-hidden="true" />
              <span>{c.quote}</span>
            </div>
          </button>
        );
      })}
      {extraUnverified.map((c, i) => (
        <div key={`unverified-${i}`} className="citation-item unverified">
          <div className="citation-head">
            <div className="citation-meta">
              <span className="citation-number" aria-hidden="true">
                {c.source}
              </span>
              <span className="citation-path">Source not retrieved</span>
            </div>
            <span className="citation-status unverified">
              <AlertTriangleIcon aria-hidden="true" />
              Unverified
            </span>
          </div>
          <div className="citation-quote">
            <QuoteIcon aria-hidden="true" />
            <span>{c.quote}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function AnswerDetails({
  supportingPoints,
  caveats,
}: {
  supportingPoints: string[];
  caveats: string[];
}) {
  if (supportingPoints.length === 0 && caveats.length === 0) return null;

  return (
    <div className="answer-details">
      {supportingPoints.length > 0 && (
        <div className="answer-detail-block">
          <div className="answer-detail-title">
            <SparkleIcon aria-hidden="true" />
            Key details
          </div>
          <ul>
            {supportingPoints.map((point, i) => (
              <li key={`point-${i}`}>{point}</li>
            ))}
          </ul>
        </div>
      )}
      {caveats.length > 0 && (
        <div className="answer-detail-block answer-detail-caveats">
          <div className="answer-detail-title">
            <InfoIcon aria-hidden="true" />
            Caveats
          </div>
          <ul>
            {caveats.map((item, i) => (
              <li key={`caveat-${i}`}>{item}</li>
            ))}
          </ul>
        </div>
      )}
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
        {messages.length === 0 && !isRunning && (
          <div className="thread-empty">
            <MessageIcon className="thread-empty-icon" aria-hidden="true" />
            Ask a question about your documents in German or English. Answers
            include verified, clickable source citations.
          </div>
        )}
        {messages.map((m) => {
          const text = m.content
            .filter((p): p is { type: "text"; text: string } => p.type === "text")
            .map((p) => p.text)
            .join("");
          const meta = (m.metadata?.custom ?? {}) as CustomMeta;

          return (
            <div key={m.id} className={`message-row ${m.role}`}>
              <div className="message-bubble">{text}</div>
              {m.role === "assistant" && (
                <AnswerDetails
                  supportingPoints={meta.supporting_points ?? []}
                  caveats={meta.caveats ?? []}
                />
              )}
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
            <div className="message-bubble">
              <span className="typing-indicator" aria-label="Assistant is typing">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}
      </div>
      <div className="composer">
        <input
          value={input}
          placeholder="Frage stellen / Ask a question…"
          aria-label="Question"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          disabled={isRunning}
        />
        <button onClick={send} disabled={isRunning || !input.trim()} aria-label="Send">
          <SendIcon aria-hidden="true" />
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
            <div className="app-title">
              <span className="app-title-icon">
                <DocumentIcon aria-hidden="true" />
              </span>
              Local RAG — Document Assistant
            </div>
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
