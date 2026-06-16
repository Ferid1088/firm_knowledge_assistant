"use client";

import { useEffect, useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  useThread,
  useThreadRuntime,
} from "@assistant-ui/react";
import { ragChatAdapter, setActiveConversationId, setActiveLangCodes } from "@/lib/chatAdapter";
import type { ArtifactChunk, Claim, ConversationDetail, ConversationSummary, User } from "@/lib/types";
import { PdfViewer } from "@/components/PdfViewer";
import { UploadPdf } from "@/components/UploadPdf";
import { ConversationSidebar } from "@/components/ConversationSidebar";
import { getMe } from "@/lib/auth";
import {
  AlertTriangleIcon,
  ChevronRightIcon,
  FileTextIcon,
  MessageSquareIcon,
  QuoteIcon,
  SendIcon,
} from "@/components/icons";

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
  return <span className={`confidence-badge ${cls}`}>Confidence {pct}%</span>;
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

  if (chunks.length === 0 && unverified.length === 0 && verifiedSources.size === 0) return null;

  return (
    <div className="citations">
      {chunks.map((c, i) => {
        const headingPath = c.address.heading_path.filter(Boolean);
        return (
          <button key={`${c.chunk_id}-${i}`} className="citation-item" onClick={() => onSelect(c)}>
            <span className="citation-badge">{c.source}</span>
            <span className="citation-body">
              <span className="citation-meta">
                <FileTextIcon />
                <span className="citation-heading-crumb">
                  {(headingPath.length > 0 ? headingPath : [c.address.doc_id]).map((part, idx) => (
                    <span key={idx} style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
                      {idx > 0 && <ChevronRightIcon />}
                      <span>{part}</span>
                    </span>
                  ))}
                </span>
                {c.address.page != null && <span className="citation-page">p. {c.address.page + 1}</span>}
              </span>
              <span className="citation-quote">
                <QuoteIcon />
                <span>{c.quote}</span>
              </span>
            </span>
          </button>
        );
      })}
      {unverified.map((c, i) => (
        <div key={`unverified-${i}`} className="citation-item unverified">
          <span className="citation-badge">{c.source}</span>
          <span className="citation-body">
            <span className="citation-unverified-tag">
              <AlertTriangleIcon /> Unverified citation
            </span>
            <span className="citation-quote">
              <QuoteIcon />
              <span>{c.quote}</span>
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function HistoryMessages({
  messages,
  onSelectChunk,
}: {
  messages: ConversationDetail["messages"];
  onSelectChunk: (chunk: ArtifactChunk) => void;
}) {
  if (messages.length === 0) return null;
  return (
    <div className="history-viewport">
      {messages.map((m) => (
        <div key={m.id} className={`message-row ${m.role}`}>
          <div className="message-bubble">
            {m.text}
            {!m.integrity_verified && (
              <div className="integrity-warning">
                <AlertTriangleIcon /> Integrity check failed
              </div>
            )}
          </div>
          {m.role === "assistant" && (m.artifact_chunks?.length || m.claims?.length) > 0 && (
            <Citations chunks={m.artifact_chunks} claims={m.claims} onSelect={onSelectChunk} />
          )}
        </div>
      ))}
      <div className="history-divider">New messages</div>
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
          <div className="message-row assistant typing">
            <div className="message-bubble">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
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
        <button onClick={send} disabled={isRunning || !input.trim()} aria-label="Senden / Send">
          <SendIcon />
        </button>
      </div>
    </>
  );
}

function ChatPane({
  history,
  onSelectChunk,
}: {
  history: ConversationDetail["messages"];
  onSelectChunk: (chunk: ArtifactChunk) => void;
}) {
  const runtime = useLocalRuntime(ragChatAdapter);
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <HistoryMessages messages={history} onSelectChunk={onSelectChunk} />
      <Thread onSelectChunk={onSelectChunk} />
    </AssistantRuntimeProvider>
  );
}

export default function Home() {
  const [selected, setSelected] = useState<ArtifactChunk | null>(null);
  const [jumpToken, setJumpToken] = useState(0);

  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationIdState] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg: { default_active_languages?: string[] }) => {
        if (cfg.default_active_languages) setActiveLangCodes(cfg.default_active_languages);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    getMe().then((u) => {
      if (u) {
        setCurrentUser(u);
        refreshConversations();
      }
    });
  }, []);

  function refreshConversations() {
    fetch("/api/conversations", { credentials: "include" })
      .then((r) => r.json())
      .then((data: ConversationSummary[]) => {
        setConversations(data);
        if (!activeConversationId && data.length > 0) {
          setActiveConversationIdState(data[0].id);
        }
      })
      .catch(() => {});
  }

  useEffect(() => {
    setActiveConversationId(activeConversationId);
    if (!activeConversationId) {
      setActiveConversation(null);
      return;
    }
    fetch(`/api/conversations/${activeConversationId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((data: ConversationDetail) => setActiveConversation(data))
      .catch(() => setActiveConversation(null));
  }, [activeConversationId]);

  return (
    <div id="app-root">
      <ConversationSidebar
        currentUser={currentUser}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={setActiveConversationIdState}
        onConversationsChanged={refreshConversations}
      />
      <div className="chat-pane">
        <div className="app-header">
          <span className="app-header-title">
            <span className="app-header-icon">
              <MessageSquareIcon />
            </span>
            {activeConversation?.title ?? "Local RAG — Document Assistant"}
          </span>
          <UploadPdf />
        </div>
        {activeConversationId ? (
          <ChatPane
            key={activeConversationId}
            history={activeConversation?.messages ?? []}
            onSelectChunk={(chunk) => {
              setSelected(chunk);
              setJumpToken((t) => t + 1);
            }}
          />
        ) : (
          <div className="conversation-empty">
            <MessageSquareIcon />
            Create or select a conversation to start chatting.
          </div>
        )}
      </div>
      <div className="viewer-pane">
        <PdfViewer docId={selected?.address.doc_id ?? null} highlight={selected} jumpToken={jumpToken} />
      </div>
    </div>
  );
}
