"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  useThread,
  useThreadRuntime,
} from "@assistant-ui/react";
import { ragChatAdapter, setActiveConversationId, setActiveLangCodes } from "@/lib/chatAdapter";
import type { ArtifactChunk, ConversationDetail, ConversationSummary, User } from "@/lib/types";
import { PdfViewer } from "@/components/PdfViewer";
import { ConversationSidebar } from "@/components/ConversationSidebar";
import { getMe } from "@/lib/auth";
import {
  AlertTriangleIcon,
  ChevronRightIcon,
  FileTextIcon,
  LangfuseIcon,
  MessageSquareIcon,
  PinIcon,
  ShieldCheckIcon,
  QuoteIcon,
  SendIcon,
} from "@/components/icons";

type CustomMeta = {
  answer_lang?: string;
  confidence?: number;
  attempts?: number;
  claims?: unknown[];
  artifact_chunks?: ArtifactChunk[];
};

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const cls = confidence >= 0.5 ? "confidence-high" : "confidence-low";
  return <span className={`confidence-badge ${cls}`}>Confidence {pct}%</span>;
}

function Citations({
  chunks,
  onSelect,
}: {
  chunks: ArtifactChunk[];
  onSelect: (chunk: ArtifactChunk) => void;
}) {
  if (chunks.length === 0) return null;

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
          <div className="message-meta">
            <span className="message-role">{m.role === "assistant" ? "Assistant" : "You"}</span>
            {m.role === "assistant" && m.integrity_verified && (
              <span className="message-tag success">
                <ShieldCheckIcon /> Verified
              </span>
            )}
          </div>
          <div className="message-bubble">
            {m.text}
            {!m.integrity_verified && (
              <div className="integrity-warning">
                <AlertTriangleIcon /> Integrity check failed
              </div>
            )}
          </div>
          {m.role === "assistant" && (m.artifact_chunks?.length || m.claims?.length) > 0 && (
            <Citations chunks={m.artifact_chunks} onSelect={onSelectChunk} />
          )}
        </div>
      ))}
    </div>
  );
}

function Thread({
  onSelectChunk,
  onFirstMessage,
}: {
  onSelectChunk: (chunk: ArtifactChunk) => void;
  onFirstMessage?: (text: string) => void;
}) {
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
    // Auto-title: fire on the very first user message
    const userMessages = messages.filter((m) => m.role === "user");
    if (userMessages.length === 0) onFirstMessage?.(text);
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
              <div className="message-meta">
                <span className="message-role">{m.role === "assistant" ? "Assistant" : "You"}</span>
                {m.role === "assistant" && meta.confidence !== undefined && (
                  <span className="message-tag">Evidence-based answer</span>
                )}
              </div>
              <div className="message-bubble">{text}</div>
              {m.role === "assistant" && meta.confidence !== undefined && (
                <ConfidenceBadge confidence={meta.confidence} />
              )}
              {m.role === "assistant" && (meta.artifact_chunks?.length ?? 0) > 0 && (
                <Citations
                  chunks={meta.artifact_chunks ?? []}
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
  onFirstMessage,
}: {
  history: ConversationDetail["messages"];
  onSelectChunk: (chunk: ArtifactChunk) => void;
  onFirstMessage?: (text: string) => void;
}) {
  const runtime = useLocalRuntime(ragChatAdapter);
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <HistoryMessages messages={history} onSelectChunk={onSelectChunk} />
      <Thread onSelectChunk={onSelectChunk} onFirstMessage={onFirstMessage} />
    </AssistantRuntimeProvider>
  );
}

export default function Home() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<ArtifactChunk | null>(null);
  const [jumpToken, setJumpToken] = useState(0);

  const [sidebarWidth, setSidebarWidth] = useState(312);
  const [chatWidth, setChatWidth] = useState(760);
  const [dragging, setDragging] = useState<null | "sidebar" | "chat">(null);

  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationIdState] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(null);

  const RESIZER_WIDTH = 18;
  const MIN_SIDEBAR_WIDTH = 260;
  const MIN_CHAT_WIDTH = 420;
  const MIN_VIEWER_WIDTH = 360;

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

  async function autoTitleConversation(question: string) {
    if (!activeConversationId) return;
    const title = question.length > 60 ? question.slice(0, 57).trimEnd() + "…" : question;
    await fetch(`/api/conversations/${activeConversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ title }),
    });
    refreshConversations();
  }

  function refreshConversations() {
    fetch("/api/conversations", { credentials: "include" })
      .then((r) => r.json())
      .then((data: ConversationSummary[]) => {
        if (!Array.isArray(data)) return;
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

  useEffect(() => {
    if (!dragging) return;

    function clamp(value: number, min: number, max: number) {
      return Math.min(Math.max(value, min), max);
    }

    function onMouseMove(event: MouseEvent) {
      const root = rootRef.current;
      if (!root) return;

      const rect = root.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const maxSidebar = rect.width - MIN_CHAT_WIDTH - MIN_VIEWER_WIDTH - RESIZER_WIDTH * 2;

      if (dragging === "sidebar") {
        const nextSidebarWidth = clamp(x - RESIZER_WIDTH / 2, MIN_SIDEBAR_WIDTH, maxSidebar);
        const maxChatWidth = rect.width - nextSidebarWidth - MIN_VIEWER_WIDTH - RESIZER_WIDTH * 2;
        setSidebarWidth(nextSidebarWidth);
        setChatWidth((prev) => clamp(prev, MIN_CHAT_WIDTH, maxChatWidth));
        return;
      }

      const maxChatWidth = rect.width - sidebarWidth - MIN_VIEWER_WIDTH - RESIZER_WIDTH * 2;
      const nextChatWidth = clamp(x - sidebarWidth - RESIZER_WIDTH - RESIZER_WIDTH / 2, MIN_CHAT_WIDTH, maxChatWidth);
      setChatWidth(nextChatWidth);
    }

    function onMouseUp() {
      setDragging(null);
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [dragging, sidebarWidth]);

  return (
    <div id="app-root" ref={rootRef} className={dragging ? "is-resizing" : undefined}>
      <ConversationSidebar
        currentUser={currentUser}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={setActiveConversationIdState}
        onConversationsChanged={refreshConversations}
        style={{ width: sidebarWidth, flex: `0 0 ${sidebarWidth}px` } as CSSProperties}
      />
      <div
        className={`column-resizer ${dragging === "sidebar" ? "active" : ""}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        onMouseDown={() => setDragging("sidebar")}
      />
      <div className="chat-pane" style={{ width: chatWidth, flex: `0 0 ${chatWidth}px` } as CSSProperties}>
        <div className="app-header">
          <div className="app-header-main">
            <span className="app-header-title">
              <span className="app-header-icon">
                <MessageSquareIcon />
              </span>
              <span className="app-header-copy">
                <strong>{activeConversation?.title ?? "Document intelligence workspace"}</strong>
                <span>
                  {activeConversationId
                    ? "Chat with cited answers and open supporting evidence instantly."
                    : "Select a conversation to explore your document knowledge base."}
                </span>
              </span>
            </span>
          </div>
          <div className="app-header-stats">
            <a
              href="http://localhost:3001"
              target="_blank"
              rel="noopener noreferrer"
              className="langfuse-btn"
              title="Open Langfuse observability"
            >
              <LangfuseIcon />
            </a>
            <span className="header-chip">
              <ShieldCheckIcon /> Secure
            </span>
            <span className="header-chip subtle">
              <PinIcon /> {selected ? `Page ${selected.address.page != null ? selected.address.page + 1 : "source"}` : "No citation selected"}
            </span>
          </div>
        </div>
        {activeConversationId ? (
          <ChatPane
            key={activeConversationId}
            history={activeConversation?.messages ?? []}
            onSelectChunk={(chunk) => {
              setSelected(chunk);
              setJumpToken((t) => t + 1);
            }}
            onFirstMessage={autoTitleConversation}
          />
        ) : (
          <div className="conversation-empty">
            <div className="conversation-empty-hero">
              <span className="conversation-empty-badge">Modern workspace</span>
              <MessageSquareIcon />
              <h2>Your answers, evidence, and documents in one place.</h2>
              <p>Create or select a conversation to start chatting with your knowledge base.</p>
            </div>
          </div>
        )}
      </div>
      <div
        className={`column-resizer ${dragging === "chat" ? "active" : ""}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize chat panel"
        onMouseDown={() => setDragging("chat")}
      />
      <div className="viewer-pane">
        <PdfViewer docId={selected?.address.doc_id ?? null} highlight={selected} jumpToken={jumpToken} />
      </div>
    </div>
  );
}
