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
  CloseIcon,
  FileTextIcon,
  HelpCircleIcon,
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
                {c.address.page != null && <span className="citation-page">p. {c.address.page}</span>}
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

function HelpOverlay({ onClose }: { onClose: () => void }) {
  return (
    <div className="help-overlay" role="dialog" aria-modal="true" aria-label="Help guide" onClick={onClose}>
      <div className="help-modal" onClick={(e) => e.stopPropagation()}>
        <div className="help-modal-header">
          <span className="help-modal-title">
            <HelpCircleIcon /> How to use this workspace
          </span>
          <button className="help-modal-close" onClick={onClose} aria-label="Close help">
            <CloseIcon />
          </button>
        </div>

        <div className="help-modal-body">
          <div className="help-section">
            <h3>Getting started</h3>
            <ol className="help-steps">
              <li>Upload a PDF using the <strong>Upload</strong> button in the left sidebar.</li>
              <li>Click <strong>New conversation</strong> to open a chat session.</li>
              <li>Type your question in German or English — the system auto-detects the language.</li>
              <li>Click a citation card below the answer to jump to the exact page in the PDF viewer.</li>
            </ol>
          </div>

          <div className="help-section">
            <h3>Asking good questions</h3>
            <ul className="help-list">
              <li>Be specific: <em>"What is the maximum load for bolt M12 in table 3?"</em></li>
              <li>Use exact part numbers or clause references for precise results.</li>
              <li>Multi-part questions work: <em>"Compare section 4.1 and 4.2 on safety requirements."</em></li>
              <li>If the answer shows low confidence, try rephrasing or adding more context.</li>
            </ul>
          </div>

          <div className="help-section">
            <h3>Understanding the answer</h3>
            <div className="help-legend">
              <div className="help-legend-item">
                <span className="confidence-badge confidence-high" style={{ pointerEvents: "none" }}>Confidence 87%</span>
                <span>High confidence — answer well-supported by documents</span>
              </div>
              <div className="help-legend-item">
                <span className="confidence-badge confidence-low" style={{ pointerEvents: "none" }}>Confidence 40%</span>
                <span>Low confidence — answer may be incomplete or uncertain</span>
              </div>
              <div className="help-legend-item">
                <span className="message-tag success" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, padding: "3px 8px", borderRadius: 999 }}><ShieldCheckIcon /> Verified</span>
                <span>All cited quotes were verified against the source text</span>
              </div>
            </div>
          </div>

          <div className="help-section">
            <h3>PDF viewer</h3>
            <ul className="help-list">
              <li>Click any citation card to jump to the exact page and highlight the passage.</li>
              <li>Drag the column dividers to resize the sidebar, chat, and viewer panels.</li>
              <li>The viewer shows coloured overlay rectangles over cited text.</li>
            </ul>
          </div>

          <div className="help-section">
            <h3>Conversations & sharing</h3>
            <ul className="help-list">
              <li>Each conversation is private to you by default.</li>
              <li>Use the <strong>share icon</strong> on a conversation to grant another user access.</li>
              <li>Rename a conversation by clicking the <strong>pencil icon</strong>.</li>
              <li>Archive or delete conversations from the sidebar action buttons.</li>
            </ul>
          </div>
        </div>

        <div className="help-modal-footer">
          <span className="help-footer-note">All processing is local and air-gapped — no data leaves the network.</span>
          <button className="admin-btn admin-btn-primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
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

  const [showHelp, setShowHelp] = useState(false);
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
            <button
              className="help-btn"
              onClick={() => setShowHelp(true)}
              title="Help & guide"
              aria-label="Open help guide"
            >
              <HelpCircleIcon />
            </button>
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
      {showHelp && <HelpOverlay onClose={() => setShowHelp(false)} />}
    </div>
  );
}
