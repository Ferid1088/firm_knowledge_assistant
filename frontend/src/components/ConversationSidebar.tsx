"use client";

import { useEffect, useState, type CSSProperties } from "react";
import type { ConversationDetail, ConversationSummary, Department, User } from "@/lib/types";
import { UploadPdf } from "@/components/UploadPdf";

import {
  ArchiveIcon,
  ArchiveRestoreIcon,
  CloseIcon,
  FileTextIcon,
  MessageSquareIcon,
  PencilIcon,
  PlusIcon,
  ShareIcon,
  TrashIcon,
} from "@/components/icons";

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

  // Department filter state
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedDeptIds, setSelectedDeptIds] = useState<string[]>([]); // empty = All
  const [filterOpen, setFilterOpen] = useState(false);

  useEffect(() => {
    fetch("/api/departments/allowed", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Department[]) => {
        if (!Array.isArray(data)) return;
        setDepartments(data);
      })
      .catch(() => {});
  }, [currentUser]);

  const allChecked = selectedDeptIds.length === 0;

  function toggleDeptId(id: string) {
    const current = selectedDeptIds.length === 0
      ? departments.map((d) => d.id)
      : selectedDeptIds;
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id];
    setSelectedDeptIds(next.length === departments.length ? [] : next);
  }

  function toggleAll() {
    setSelectedDeptIds([]);
  }

  function isChecked(id: string) {
    return selectedDeptIds.length === 0 || selectedDeptIds.includes(id);
  }

  function filterLabel() {
    if (selectedDeptIds.length === 0) return "Alle";
    if (selectedDeptIds.length === 1) {
      const d = departments.find((d) => d.id === selectedDeptIds[0]);
      return d ? d.name : "1 Abt.";
    }
    return `${selectedDeptIds.length} Abt.`;
  }

  // Filter conversations by selected departments (client-side)
  const visibleConversations = selectedDeptIds.length === 0
    ? conversations
    : conversations.filter((c) => selectedDeptIds.includes(c.department_id));

  useEffect(() => {
    if (!shareOpenFor) {
      setShares([]);
      return;
    }
    fetch(`/api/conversations/${shareOpenFor}`, { headers: authHeaders(), credentials: "include" })
      .then((r) => r.json())
      .then((data: ConversationDetail) => setShares(data.shares ?? []))
      .catch(() => setShares([]));
  }, [shareOpenFor]);

  async function createConversation() {
    const res = await fetch("/api/conversations", {
      method: "POST",
      headers: authHeaders(),
      credentials: "include",
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
    await fetch(`/api/conversations/${id}`, {
      method: "PATCH",
      headers: authHeaders(),
      credentials: "include",
      body: JSON.stringify({ title }),
    });
    onConversationsChanged();
  }

  async function setStatus(id: string, status: "archived" | "deleted" | "active") {
    await fetch(`/api/conversations/${id}`, {
      method: "PATCH",
      headers: authHeaders(),
      credentials: "include",
      body: JSON.stringify({ status }),
    });
    onConversationsChanged();
  }

  async function share(id: string) {
    if (!shareTargetUser) return;
    await fetch(`/api/conversations/${id}/share`, {
      method: "POST",
      headers: authHeaders(),
      credentials: "include",
      body: JSON.stringify({ user_id: shareTargetUser, permission: sharePermission }),
    });
    const res = await fetch(`/api/conversations/${id}`, { headers: authHeaders(), credentials: "include" });
    const data: ConversationDetail = await res.json();
    setShares(data.shares ?? []);
  }

  async function revokeShare(id: string, userId: string) {
    await fetch(`/api/conversations/${id}/share/${userId}`, {
      method: "DELETE",
      headers: authHeaders(),
      credentials: "include",
    });
    const res = await fetch(`/api/conversations/${id}`, { headers: authHeaders(), credentials: "include" });
    const data: ConversationDetail = await res.json();
    setShares(data.shares ?? []);
  }

  return (
    <div className="conversation-sidebar" style={style}>
      {/* Brand */}
      <div className="sidebar-section">
        <div className="sidebar-brand">
          <span className="app-header-icon"><FileTextIcon /></span>
          Local RAG
        </div>
      </div>

      {/* Upload */}
      <div className="sidebar-section sidebar-section-upload">
        <UploadPdf allowedDocTypeIds={currentUser?.allowed_doc_type_ids ?? null} />
      </div>

      {/* Department filter */}
      {departments.length > 0 && (
        <div className="sidebar-section sidebar-filter-section">
          <div className="sidebar-filter-label">Filter nach Department</div>
          <div className="sidebar-filter-dropdown">
            <button
              className={`sidebar-filter-trigger ${filterOpen ? "open" : ""}`}
              onClick={() => setFilterOpen((v) => !v)}
              type="button"
            >
              <span className="sidebar-filter-trigger-label">{filterLabel()}</span>
              <span className="sidebar-filter-trigger-arrow">{filterOpen ? "▲" : "▼"}</span>
            </button>

            {filterOpen && (
              <>
                <div className="sidebar-filter-backdrop" onClick={() => setFilterOpen(false)} />
                <div className="sidebar-filter-panel">
                  <label className="sidebar-filter-option">
                    <input type="checkbox" checked={allChecked} onChange={toggleAll} />
                    <span className="sidebar-filter-option-name">Alle</span>
                  </label>
                  <div className="sidebar-filter-divider" />
                  {departments.map((d) => (
                    <label key={d.id} className="sidebar-filter-option">
                      <input
                        type="checkbox"
                        checked={isChecked(d.id)}
                        onChange={() => toggleDeptId(d.id)}
                      />
                      <span className="sidebar-filter-code">#{d.code}</span>
                      <span className="sidebar-filter-option-name">{d.name}</span>
                    </label>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* New conversation */}
      <div className="sidebar-section">
        <button className="sidebar-new-btn" onClick={createConversation}>
          <PlusIcon />
          New conversation
        </button>
      </div>

      {/* Conversation list */}
      <div className="conversation-list">
        {visibleConversations.map((c) => (
          <div key={c.id} className={`conversation-item ${c.id === activeConversationId ? "active" : ""}`}>
            <div className="conversation-item-title" onClick={() => onSelectConversation(c.id)}>
              <MessageSquareIcon />
              <span className="conversation-item-title-text">{c.title}</span>
              {c.status !== "active" && <span className="conversation-status">{c.status}</span>}
            </div>
            <div className="conversation-item-actions">
              <button className="icon-btn" title="Rename" aria-label="Rename conversation"
                onClick={() => renameConversation(c.id, c.title)}><PencilIcon /></button>
              {c.status !== "archived" ? (
                <button className="icon-btn" title="Archive" aria-label="Archive conversation"
                  onClick={() => setStatus(c.id, "archived")}><ArchiveIcon /></button>
              ) : (
                <button className="icon-btn" title="Restore" aria-label="Restore conversation"
                  onClick={() => setStatus(c.id, "active")}><ArchiveRestoreIcon /></button>
              )}
              <button className="icon-btn danger" title="Delete" aria-label="Delete conversation"
                onClick={() => setStatus(c.id, "deleted")}><TrashIcon /></button>
              <button
                className={`icon-btn ${shareOpenFor === c.id ? "active" : ""}`}
                title="Share" aria-label="Share conversation"
                onClick={() => setShareOpenFor(shareOpenFor === c.id ? null : c.id)}
              ><ShareIcon /></button>
            </div>
            {shareOpenFor === c.id && (
              <div className="share-panel">
                {shares.map((s) => (
                  <div key={s.user_id} className="share-row">
                    <span>{s.user_id} <span className="share-permission">({s.permission})</span></span>
                    <button className="icon-btn" title="Revoke access" aria-label="Revoke access"
                      onClick={() => revokeShare(c.id, s.user_id)}><CloseIcon /></button>
                  </div>
                ))}
                <div className="share-row">
                  <input type="text" placeholder="User ID to share with…"
                    value={shareTargetUser} onChange={(e) => setShareTargetUser(e.target.value)} />
                  <select value={sharePermission} onChange={(e) => setSharePermission(e.target.value)}>
                    <option value="view">view</option>
                    <option value="comment">comment</option>
                    <option value="edit">edit</option>
                  </select>
                  <button className="icon-btn" title="Share" aria-label="Confirm share"
                    onClick={() => share(c.id)}><ShareIcon /></button>
                </div>
              </div>
            )}
          </div>
        ))}
        {visibleConversations.length === 0 && (
          <div className="sidebar-empty">
            <MessageSquareIcon />
            {selectedDeptIds.length > 0 ? "Keine Gespräche in diesem Department." : "No conversations yet."}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="sidebar-footer">
        <span className="sidebar-user-name">{currentUser?.name ?? "…"}</span>
        {currentUser?.role_id === "superadmin" && (
          <a href="/admin" className="sidebar-icon-btn" title="Admin panel" aria-label="Admin panel">⚙</a>
        )}
        <button
          className="sidebar-logout-btn"
          onClick={async () => {
            const { logout } = await import("@/lib/auth");
            await logout();
            window.location.href = "/login";
          }}
        >
          Logout
        </button>
      </div>
    </div>
  );
}
