"use client";

import { useEffect, useRef, useState } from "react";
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
import { AppShell } from "@/components/AppShell";
import { getMe } from "@/lib/auth";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Tooltip } from "@/components/ui/Tooltip";
import { ConfidenceMeter } from "@/components/korpus/ConfidenceMeter";
import {
  Search,
  ArrowUp,
  FileText,
  ChevronRight,
  Quote,
  ShieldCheck,
  CircleCheck,
  TriangleAlert,
  ThumbsUp,
  Copy,
  Lock,
  MessageSquare,
  X,
  ExternalLink,
} from "lucide-react";

type CustomMeta = {
  answer_lang?: string;
  confidence?: number;
  attempts?: number;
  claims?: unknown[];
  artifact_chunks?: ArtifactChunk[];
};

function ConfidenceBadgeInline({ confidence }: { confidence: number }) {
  const level = confidence >= 0.7 ? "high" : confidence >= 0.4 ? "moderate" : "low";
  return <ConfidenceMeter level={level} />;
}

function CitationCard({
  chunk,
  index,
  onSelect,
}: {
  chunk: ArtifactChunk;
  index: number;
  onSelect: (chunk: ArtifactChunk) => void;
}) {
  const headingPath = chunk.address.heading_path.filter(Boolean);
  const typeColor = "var(--accent-500)";

  return (
    <div
      onClick={() => onSelect(chunk)}
      style={{
        display: "flex", gap: 10, padding: "11px 12px",
        background: "var(--surface-card)",
        border: "1px solid var(--border-default)",
        borderLeft: `2px solid ${typeColor}`,
        borderRadius: "var(--r-md)", cursor: "pointer",
        transition: "background var(--dur-fast) var(--ease-out)",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-hover)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "var(--surface-card)")}
    >
      <span style={{
        flex: "none", width: 20, height: 20, borderRadius: "var(--r-xs)",
        background: "var(--accent-tint)", color: "var(--accent-300)",
        fontFamily: "var(--font-mono)", fontSize: "var(--fs-2xs)", fontWeight: 600,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
      }}>{index}</span>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
          <FileText size={13} color="var(--text-muted)" />
          <span style={{
            fontFamily: "var(--font-sans)", fontSize: "var(--fs-sm)", fontWeight: 600,
            color: "var(--text-strong)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {headingPath.length > 0 ? headingPath.join(" > ") : chunk.address.doc_id}
          </span>
          {chunk.address.page != null && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-2xs)", color: "var(--text-muted)", flex: "none" }}>
              p. {chunk.address.page + 1}
            </span>
          )}
          <span style={{ flex: 1 }} />
          <span style={{ display: "inline-flex", alignItems: "center", gap: 3, color: "var(--verify-300)", fontSize: "var(--fs-2xs)", fontWeight: 600, flex: "none" }}>
            <CircleCheck size={13} color="var(--verify-500)" /> Source
          </span>
        </div>
        {chunk.quote && (
          <blockquote style={{
            margin: 0, paddingLeft: 9, borderLeft: "2px solid var(--border-strong)",
            fontSize: "var(--fs-sm)", lineHeight: "var(--lh-snug)", color: "var(--text-body)",
          }}>&ldquo;{chunk.quote}&rdquo;</blockquote>
        )}
      </div>
    </div>
  );
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
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
      <span className="k-eyebrow">{chunks.length} sources</span>
      {chunks.map((c, i) => (
        <CitationCard key={`${c.chunk_id}-${i}`} chunk={c} index={i + 1} onSelect={onSelect} />
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
    <div style={{
      padding: "16px 16px 8px", display: "flex", flexDirection: "column", gap: 14,
      borderBottom: "1px solid var(--border-subtle)", maxHeight: "40vh", overflowY: "auto",
    }}>
      {messages.map((m) => (
        <div key={m.id} style={{ display: "flex", gap: 11 }}>
          <span style={{
            flex: "none", width: 24, height: 24, borderRadius: "var(--r-sm)",
            background: m.role === "assistant" ? "var(--surface-raised)" : "var(--accent-900)",
            border: "1px solid var(--border-default)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            color: m.role === "assistant" ? "var(--text-secondary)" : "var(--accent-300)",
            fontFamily: "var(--font-sans)", fontSize: 10, fontWeight: 600,
          }}>
            {m.role === "assistant" ? "K" : "U"}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{
              margin: 0, fontSize: "var(--fs-body)", lineHeight: "var(--lh-relaxed)",
              color: "var(--text-body)",
            }}>{m.text}</p>
            {m.role === "assistant" && !m.integrity_verified && (
              <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4, color: "var(--warn-300)", fontSize: "var(--fs-xs)", fontWeight: 600 }}>
                <TriangleAlert size={12} color="var(--warn-500)" /> Integrity check failed
              </div>
            )}
            {m.role === "assistant" && (m.artifact_chunks?.length > 0) && (
              <Citations chunks={m.artifact_chunks} onSelect={onSelectChunk} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function Thread({
  onSelectChunk,
  onFirstMessage,
  hasHistory = false,
}: {
  onSelectChunk: (chunk: ArtifactChunk) => void;
  onFirstMessage?: (text: string) => void;
  hasHistory?: boolean;
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
    const userMessages = messages.filter((m) => m.role === "user");
    if (userMessages.length === 0) onFirstMessage?.(text);
    runtime.append(text);
    setInput("");
  }

  return (
    <>
      <div ref={viewportRef} style={{ flex: 1, overflowY: "auto", padding: "22px 0" }}>
        <div style={{ maxWidth: "var(--content-max)", margin: "0 auto", padding: "0 26px" }}>
          {messages.length === 0 && !isRunning && !hasHistory && (
            <div style={{ marginTop: 56, textAlign: "center" }}>
              <img src="/korpus-mark.svg" width={46} height={46} alt="" style={{ opacity: 0.9 }} />
              <h1 style={{ margin: "16px 0 6px", fontSize: "var(--fs-h1)", fontWeight: 600, color: "var(--text-strong)", letterSpacing: "-0.01em" }}>
                Ask your documents anything
              </h1>
              <p style={{ margin: "0 auto", maxWidth: 440, fontSize: "var(--fs-body)", color: "var(--text-secondary)", lineHeight: "var(--lh-normal)" }}>
                Every answer is grounded in your indexed corpus and cited to the exact page. Nothing leaves the building.
              </p>
            </div>
          )}
          {messages.map((m) => {
            const text = m.content
              .filter((p): p is { type: "text"; text: string } => p.type === "text")
              .map((p) => p.text)
              .join("");
            const meta = (m.metadata?.custom ?? {}) as CustomMeta;

            return (
              <div key={m.id} style={{ display: "flex", gap: 11, marginBottom: 20 }}>
                <span style={{
                  flex: "none", width: 24, height: 24, borderRadius: "var(--r-sm)",
                  background: m.role === "assistant" ? "var(--surface-raised)" : "var(--accent-900)",
                  border: "1px solid var(--border-default)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  overflow: "hidden",
                }}>
                  {m.role === "assistant"
                    ? <img src="/korpus-mark.svg" width={16} height={16} alt="" />
                    : <span style={{ color: "var(--accent-300)", fontFamily: "var(--font-sans)", fontSize: 10, fontWeight: 600 }}>U</span>
                  }
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{
                    margin: 0, fontSize: "var(--fs-body)", lineHeight: "var(--lh-relaxed)",
                    color: m.role === "user" ? "var(--text-strong)" : "var(--text-body)",
                    fontWeight: m.role === "user" ? 500 : 400,
                  }}>{text}</p>
                  {m.role === "assistant" && meta.confidence !== undefined && (
                    <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border-subtle)" }}>
                      <ConfidenceBadgeInline confidence={meta.confidence} />
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: "var(--fs-2xs)", color: "var(--verify-300)" }}>
                        <CircleCheck size={12} color="var(--verify-500)" /> Integrity verified
                      </span>
                      <span style={{ flex: 1 }} />
                      <Tooltip content="Helpful"><IconButton label="Helpful" size="sm" icon={<ThumbsUp size={15} />} /></Tooltip>
                      <Tooltip content="Copy"><IconButton label="Copy" size="sm" icon={<Copy size={15} />} /></Tooltip>
                    </div>
                  )}
                  {m.role === "assistant" && (meta.artifact_chunks?.length ?? 0) > 0 && (
                    <Citations chunks={meta.artifact_chunks ?? []} onSelect={onSelectChunk} />
                  )}
                </div>
              </div>
            );
          })}
          {isRunning && (
            <div style={{ display: "flex", gap: 11 }}>
              <span style={{
                flex: "none", width: 24, height: 24, borderRadius: "var(--r-sm)",
                background: "var(--surface-raised)", border: "1px solid var(--border-default)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
              }}>
                <img src="/korpus-mark.svg" width={16} height={16} alt="" />
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 4, paddingTop: 5 }}>
                <span style={{ display: "inline-block", width: 7, height: 15, background: "var(--accent-400)", animation: "k-caret .9s steps(1) infinite" }} />
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ flex: "none", padding: "12px 26px 18px", borderTop: "1px solid var(--border-subtle)" }}>
        <div style={{ maxWidth: "var(--content-max)", margin: "0 auto" }}>
          <div style={{
            display: "flex", alignItems: "flex-end", gap: 9,
            padding: "8px 8px 8px 14px",
            background: "var(--surface-input)", border: "1px solid var(--border-default)", borderRadius: "var(--r-md)",
          }}>
            <Search size={17} color="var(--text-muted)" style={{ marginBottom: 8 }} />
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Ask a question in German or English…"
              rows={1}
              disabled={isRunning}
              style={{
                flex: 1, resize: "none", border: "none", outline: "none", background: "transparent",
                color: "var(--text-strong)", fontFamily: "var(--font-sans)", fontSize: "var(--fs-body)",
                lineHeight: "var(--lh-normal)", padding: "6px 0", maxHeight: 120,
              }}
            />
            <Button onClick={send} disabled={isRunning || !input.trim()} iconRight={<ArrowUp size={16} color="currentColor" />}>
              Ask
            </Button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>
            <Lock size={11} color="var(--text-muted)" /> Answers are grounded only in your indexed documents. Citations are verified against source text.
          </div>
        </div>
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
      <Thread onSelectChunk={onSelectChunk} onFirstMessage={onFirstMessage} hasHistory={history.length > 0} />
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
  const [showPdf, setShowPdf] = useState(false);

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

  function selectChunk(chunk: ArtifactChunk) {
    setSelected(chunk);
    setJumpToken((t) => t + 1);
    setShowPdf(true);
  }

  return (
    <AppShell title="Ask the corpus" flush>
      <div style={{ display: "flex", height: "100%", minHeight: 0 }}>
        {/* Conversation sidebar */}
        <ConversationSidebar
          currentUser={currentUser}
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={setActiveConversationIdState}
          onConversationsChanged={refreshConversations}
          style={{
            width: 280, flex: "0 0 280px",
            borderRight: "1px solid var(--border-subtle)",
            background: "var(--bg-panel)",
            height: "100%",
          }}
        />

        {/* Chat column */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          {/* Sub-header */}
          <div style={{
            height: 46, flex: "none", display: "flex", alignItems: "center", gap: 10,
            padding: "0 14px", borderBottom: "1px solid var(--border-subtle)",
          }}>
            <span style={{
              fontSize: "var(--fs-sm)", fontWeight: 600,
              color: "var(--text-strong)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {activeConversation?.title ?? "New conversation"}
            </span>
            <Badge tone="verify" icon={<ShieldCheck size={11} color="var(--verify-500)" />}>Secure</Badge>
            <div style={{ flex: 1 }} />
            {showPdf && selected && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>
                source · p. {selected.address.page != null ? selected.address.page + 1 : "—"}
              </span>
            )}
          </div>

          {activeConversationId ? (
            <ChatPane
              key={activeConversationId}
              history={activeConversation?.messages ?? []}
              onSelectChunk={selectChunk}
              onFirstMessage={autoTitleConversation}
            />
          ) : (
            <div style={{
              flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
              gap: 10, color: "var(--text-muted)", fontSize: "var(--fs-sm)", textAlign: "center", padding: "40px 24px",
            }}>
              <img src="/korpus-mark.svg" width={46} height={46} alt="" style={{ opacity: 0.7 }} />
              <h2 style={{ margin: "12px 0 4px", fontSize: "var(--fs-h2)", fontWeight: 600, color: "var(--text-strong)" }}>
                Ask your documents anything
              </h2>
              <p style={{ margin: 0, maxWidth: 400, color: "var(--text-secondary)", lineHeight: "var(--lh-normal)" }}>
                Create or select a conversation to start chatting with your knowledge base.
              </p>
            </div>
          )}
        </div>

        {/* PDF viewer pane */}
        {showPdf && selected && (
          <aside style={{
            width: 440, flex: "0 0 440px",
            display: "flex", flexDirection: "column", minHeight: 0,
            borderLeft: "1px solid var(--border-subtle)", background: "var(--slate-925)",
          }}>
            <div style={{
              height: 46, flex: "none", display: "flex", alignItems: "center", gap: 9,
              padding: "0 12px", borderBottom: "1px solid var(--border-subtle)",
            }}>
              <FileText size={15} color="var(--text-secondary)" />
              <span style={{
                flex: 1, minWidth: 0, fontFamily: "var(--font-mono)", fontSize: "var(--fs-xs)",
                color: "var(--text-strong)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>
                {selected.address.doc_id}
              </span>
              <Badge tone="verify" icon={<CircleCheck size={11} />}>Verified</Badge>
              <Tooltip content="Open original">
                <IconButton label="Open original" size="sm" icon={<ExternalLink size={15} />} />
              </Tooltip>
              <IconButton label="Close source" size="sm" onClick={() => setShowPdf(false)} icon={<X size={16} />} />
            </div>
            <div style={{ flex: 1, overflow: "auto" }}>
              <PdfViewer
                docId={selected.address.doc_id ?? null}
                highlight={selected}
                jumpToken={jumpToken}
              />
            </div>
          </aside>
        )}
      </div>
    </AppShell>
  );
}
