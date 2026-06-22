"use client";

import { useEffect, useState, type CSSProperties } from "react";
import type { ConversationDetail, ConversationSummary, Department, User } from "@/lib/types";
import { UploadPdf } from "@/components/UploadPdf";
import {
  MessageSquare,
  Plus,
  Pencil,
  Archive,
  ArchiveRestore,
  Trash2,
  Share2,
  X,
  ChevronDown,
  LogOut,
  Settings,
  FileText,
} from "lucide-react";

function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export function ConversationSidebar({
  currentUser,
  conversations,
  activeConversationId,
  onSelectConversation,
  onConversationsChanged,
  style,
}: {
  currentUser: User | null;
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onConversationsChanged: () => void;
  style?: CSSProperties;
}) {
  const [shareOpenFor, setShareOpenFor] = useState<string | null>(null);
  const [shareTargetUser, setShareTargetUser] = useState<string>("");
  const [sharePermission, setSharePermission] = useState<string>("view");
  const [shares, setShares] = useState<ConversationDetail["shares"]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedDeptIds, setSelectedDeptIds] = useState<string[]>([]);
  const [filterOpen, setFilterOpen] = useState(false);

  useEffect(() => {
    fetch("/api/departments/allowed", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Department[]) => {
        if (Array.isArray(data)) setDepartments(data);
      })
      .catch(() => {});
  }, [currentUser]);

  const allChecked = selectedDeptIds.length === 0;
  function toggleDeptId(id: string) {
    const current = selectedDeptIds.length === 0 ? departments.map((d) => d.id) : selectedDeptIds;
    const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
    setSelectedDeptIds(next.length === departments.length ? [] : next);
  }
  function toggleAll() { setSelectedDeptIds([]); }
  function isChecked(id: string) { return selectedDeptIds.length === 0 || selectedDeptIds.includes(id); }
  function filterLabel() {
    if (selectedDeptIds.length === 0) return "All departments";
    if (selectedDeptIds.length === 1) {
      const d = departments.find((d) => d.id === selectedDeptIds[0]);
      return d ? d.name : "1 dept";
    }
    return `${selectedDeptIds.length} depts`;
  }

  const visibleConversations = selectedDeptIds.length === 0
    ? conversations
    : conversations.filter((c) => selectedDeptIds.includes(c.department_id));

  useEffect(() => {
    if (!shareOpenFor) { setShares([]); return; }
    fetch(`/api/conversations/${shareOpenFor}`, { headers: authHeaders(), credentials: "include" })
      .then((r) => r.json())
      .then((data: ConversationDetail) => setShares(data.shares ?? []))
      .catch(() => setShares([]));
  }, [shareOpenFor]);

  async function createConversation() {
    const res = await fetch("/api/conversations", {
      method: "POST", headers: authHeaders(), credentials: "include",
      body: JSON.stringify({ title: "New conversation" }),
    });
    if (res.ok) {
      const conv: ConversationSummary = await res.json();
      onConversationsChanged();
      onSelectConversation(conv.id);
    }
  }

  async function renameConversation(id: string, current: string) {
    const title = window.prompt("Rename conversation", current);
    if (!title) return;
    await fetch(`/api/conversations/${id}`, { method: "PATCH", headers: authHeaders(), credentials: "include", body: JSON.stringify({ title }) });
    onConversationsChanged();
  }

  async function setStatus(id: string, status: "archived" | "deleted" | "active") {
    await fetch(`/api/conversations/${id}`, { method: "PATCH", headers: authHeaders(), credentials: "include", body: JSON.stringify({ status }) });
    onConversationsChanged();
  }

  async function share(id: string) {
    if (!shareTargetUser) return;
    await fetch(`/api/conversations/${id}/share`, { method: "POST", headers: authHeaders(), credentials: "include", body: JSON.stringify({ user_id: shareTargetUser, permission: sharePermission }) });
    const res = await fetch(`/api/conversations/${id}`, { headers: authHeaders(), credentials: "include" });
    const data: ConversationDetail = await res.json();
    setShares(data.shares ?? []);
  }

  async function revokeShare(id: string, userId: string) {
    await fetch(`/api/conversations/${id}/share/${userId}`, { method: "DELETE", headers: authHeaders(), credentials: "include" });
    const res = await fetch(`/api/conversations/${id}`, { headers: authHeaders(), credentials: "include" });
    const data: ConversationDetail = await res.json();
    setShares(data.shares ?? []);
  }

  const actionBtn: CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    width: 26, height: 26, padding: 0, border: "none", borderRadius: "var(--r-sm)",
    background: "transparent", color: "var(--text-muted)", cursor: "pointer",
    transition: "background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out)",
  };

  return (
    <aside style={{
      display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden",
      ...style,
    }}>
      {/* Header */}
      <div style={{ padding: "14px 14px 12px", borderBottom: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 10 }}>
        <button onClick={createConversation} style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          width: "100%", height: "var(--control-h-lg)", padding: "0 14px",
          background: "var(--accent)", color: "var(--accent-fg)", border: "none",
          borderRadius: "var(--r-sm)", fontFamily: "var(--font-sans)", fontSize: "var(--fs-sm)",
          fontWeight: 600, cursor: "pointer",
          transition: "background var(--dur-fast) var(--ease-out)",
        }}
          onMouseEnter={(e) => e.currentTarget.style.background = "var(--accent-hover)"}
          onMouseLeave={(e) => e.currentTarget.style.background = "var(--accent)"}
        >
          <Plus size={16} /> New question
        </button>

        <UploadPdf allowedDocTypeIds={currentUser?.allowed_doc_type_ids ?? null} />
      </div>

      {/* Department filter */}
      {departments.length > 0 && (
        <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-subtle)", position: "relative" }}>
          <div style={{ fontSize: "var(--fs-2xs)", fontWeight: 600, letterSpacing: "var(--ls-caps)", textTransform: "uppercase" as const, color: "var(--text-muted)", marginBottom: 6 }}>
            Filter by department
          </div>
          <button onClick={() => setFilterOpen(!filterOpen)} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%",
            padding: "7px 10px", background: "var(--surface-input)", border: "1px solid var(--border-default)",
            borderRadius: "var(--r-sm)", color: "var(--text-body)", fontSize: "var(--fs-sm)",
            fontFamily: "var(--font-sans)", cursor: "pointer", textAlign: "left" as const,
          }}>
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{filterLabel()}</span>
            <ChevronDown size={14} color="var(--text-muted)" style={{ transform: filterOpen ? "rotate(180deg)" : "none", transition: "transform var(--dur-fast)" }} />
          </button>

          {filterOpen && (
            <>
              <div onClick={() => setFilterOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 399 }} />
              <div style={{
                position: "absolute", top: "calc(100% + 2px)", left: 14, right: 14, zIndex: 400,
                background: "var(--surface-raised)", border: "1px solid var(--border-strong)",
                borderRadius: "var(--r-md)", boxShadow: "var(--shadow-pop)", padding: 4, maxHeight: 220, overflowY: "auto",
              }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: "var(--r-sm)", cursor: "pointer", fontSize: "var(--fs-sm)", color: "var(--text-body)" }}
                  onMouseEnter={(e) => e.currentTarget.style.background = "var(--surface-hover)"}
                  onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                  <input type="checkbox" checked={allChecked} onChange={toggleAll} style={{ accentColor: "var(--accent)", width: 14, height: 14 }} />
                  All
                </label>
                <div style={{ height: 1, background: "var(--border-subtle)", margin: "2px 0" }} />
                {departments.map((d) => (
                  <label key={d.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: "var(--r-sm)", cursor: "pointer", fontSize: "var(--fs-sm)", color: "var(--text-body)" }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "var(--surface-hover)"}
                    onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                  >
                    <input type="checkbox" checked={isChecked(d.id)} onChange={() => toggleDeptId(d.id)} style={{ accentColor: "var(--accent)", width: 14, height: 14 }} />
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>#{d.code}</span>
                    <span>{d.name}</span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Conversation list */}
      <div style={{ flex: 1, overflowY: "auto", padding: 8, display: "flex", flexDirection: "column", gap: 2 }}>
        {visibleConversations.map((c) => {
          const isActive = c.id === activeConversationId;
          return (
            <div key={c.id} style={{
              padding: "9px 10px", borderRadius: "var(--r-sm)", cursor: "pointer",
              background: isActive ? "var(--surface-hover)" : "transparent",
              border: `1px solid ${isActive ? "var(--border-default)" : "transparent"}`,
              transition: "background var(--dur-fast) var(--ease-out)",
            }}
              onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = "var(--surface-hover)"; }}
              onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
            >
              <div onClick={() => onSelectConversation(c.id)} style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <MessageSquare size={14} style={{ flex: "none", color: isActive ? "var(--accent-300)" : "var(--text-muted)" }} />
                <span style={{
                  flex: 1, minWidth: 0, fontSize: "var(--fs-sm)", fontWeight: isActive ? 600 : 500,
                  color: isActive ? "var(--text-strong)" : "var(--text-body)",
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}>{c.title}</span>
                {c.status !== "active" && (
                  <span style={{
                    fontSize: "var(--fs-2xs)", fontWeight: 500, color: "var(--text-muted)",
                    background: "var(--surface-raised)", border: "1px solid var(--border-default)",
                    borderRadius: "var(--r-full)", padding: "1px 7px", flex: "none",
                  }}>{c.status}</span>
                )}
              </div>

              {/* Actions */}
              <div style={{
                display: "flex", gap: 2, marginTop: 6, paddingLeft: 22,
                opacity: isActive ? 1 : 0, transition: "opacity var(--dur-fast)",
              }}
                onMouseEnter={(e) => e.currentTarget.style.opacity = "1"}
                onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.opacity = "0"; }}
              >
                <button style={actionBtn} title="Rename" onClick={(e) => { e.stopPropagation(); renameConversation(c.id, c.title); }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-hover)"; e.currentTarget.style.color = "var(--text-body)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
                ><Pencil size={13} /></button>
                {c.status !== "archived" ? (
                  <button style={actionBtn} title="Archive" onClick={(e) => { e.stopPropagation(); setStatus(c.id, "archived"); }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-hover)"; e.currentTarget.style.color = "var(--text-body)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
                  ><Archive size={13} /></button>
                ) : (
                  <button style={actionBtn} title="Restore" onClick={(e) => { e.stopPropagation(); setStatus(c.id, "active"); }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-hover)"; e.currentTarget.style.color = "var(--text-body)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
                  ><ArchiveRestore size={13} /></button>
                )}
                <button style={actionBtn} title="Delete" onClick={(e) => { e.stopPropagation(); setStatus(c.id, "deleted"); }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "var(--error-tint)"; e.currentTarget.style.color = "var(--error-300)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
                ><Trash2 size={13} /></button>
                <button style={{ ...actionBtn, ...(shareOpenFor === c.id ? { background: "var(--accent-tint)", color: "var(--accent-300)" } : {}) }}
                  title="Share" onClick={(e) => { e.stopPropagation(); setShareOpenFor(shareOpenFor === c.id ? null : c.id); }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-hover)"; e.currentTarget.style.color = "var(--text-body)"; }}
                  onMouseLeave={(e) => { if (shareOpenFor !== c.id) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; } }}
                ><Share2 size={13} /></button>
              </div>

              {/* Share panel */}
              {shareOpenFor === c.id && (
                <div style={{
                  marginTop: 8, marginLeft: 22, padding: 10,
                  border: "1px solid var(--border-default)", borderRadius: "var(--r-md)",
                  background: "var(--surface-card)", display: "flex", flexDirection: "column", gap: 6,
                }}>
                  {shares.map((s) => (
                    <div key={s.user_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "var(--fs-xs)", color: "var(--text-body)" }}>
                      <span>{s.user_id} <span style={{ color: "var(--accent-300)", fontWeight: 600 }}>({s.permission})</span></span>
                      <button style={actionBtn} title="Revoke" onClick={() => revokeShare(c.id, s.user_id)}><X size={12} /></button>
                    </div>
                  ))}
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <input type="text" placeholder="User ID…" value={shareTargetUser} onChange={(e) => setShareTargetUser(e.target.value)}
                      style={{
                        flex: 1, minWidth: 0, padding: "5px 8px", fontSize: "var(--fs-xs)",
                        background: "var(--surface-input)", border: "1px solid var(--border-default)",
                        borderRadius: "var(--r-sm)", color: "var(--text-body)", fontFamily: "var(--font-sans)", outline: "none",
                      }}
                    />
                    <select value={sharePermission} onChange={(e) => setSharePermission(e.target.value)}
                      style={{
                        padding: "5px 6px", fontSize: "var(--fs-xs)",
                        background: "var(--surface-input)", border: "1px solid var(--border-default)",
                        borderRadius: "var(--r-sm)", color: "var(--text-body)", fontFamily: "var(--font-sans)", outline: "none",
                      }}
                    >
                      <option value="view">view</option>
                      <option value="comment">comment</option>
                      <option value="edit">edit</option>
                    </select>
                    <button style={actionBtn} title="Share" onClick={() => share(c.id)}><Share2 size={12} /></button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {visibleConversations.length === 0 && (
          <div style={{ padding: "28px 16px", color: "var(--text-muted)", fontSize: "var(--fs-sm)", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <MessageSquare size={24} color="var(--text-disabled)" />
            {selectedDeptIds.length > 0 ? "No conversations in this department." : "No conversations yet."}
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: "10px 14px", borderTop: "1px solid var(--border-subtle)",
        display: "flex", alignItems: "center", gap: 8, flex: "none",
      }}>
        <span style={{
          flex: "none", width: 24, height: 24, borderRadius: "var(--r-full)",
          background: "var(--accent-900)", border: "1px solid var(--border-default)",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          color: "var(--accent-300)", fontSize: 10, fontWeight: 600,
        }}>
          {(currentUser?.name ?? "U").charAt(0).toUpperCase()}
        </span>
        <span style={{ flex: 1, minWidth: 0, fontSize: "var(--fs-sm)", fontWeight: 600, color: "var(--text-strong)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {currentUser?.name ?? "…"}
        </span>
        {currentUser?.role_id === "superadmin" && (
          <a href="/admin" title="Admin panel" style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 26, height: 26, borderRadius: "var(--r-sm)",
            color: "var(--text-muted)", textDecoration: "none",
          }}><Settings size={14} /></a>
        )}
        <button
          title="Sign out"
          style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 26, height: 26, padding: 0, border: "none", borderRadius: "var(--r-sm)",
            background: "transparent", color: "var(--text-muted)", cursor: "pointer",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--error-tint)"; e.currentTarget.style.color = "var(--error-300)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-muted)"; }}
          onClick={async () => {
            const { logout } = await import("@/lib/auth");
            await logout();
            window.location.href = "/login";
          }}
        ><LogOut size={14} /></button>
      </div>
    </aside>
  );
}
