"use client";

import React, { useEffect, useState } from "react";
import type { AdminUser, Department, DocumentType, Role } from "@/lib/types";

type Tab = "users" | "departments" | "roles" | "datatypes" | "audit" | "system";

const TAB_LABELS: Record<Tab, string> = {
  users: "👥 Users",
  departments: "🏢 Departments",
  roles: "🔑 Roles",
  datatypes: "📂 Data Types",
  audit: "📋 Audit Log",
  system: "⚡ System",
};

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");

  return (
    <div className="admin-page">
      <div className="admin-header">
        <div className="admin-header-left">
          <span className="admin-header-icon">⚙</span>
          <span className="admin-header-title">Admin Panel</span>
        </div>
        <a href="/" className="admin-back">← Back to chat</a>
      </div>

      <div className="admin-tabs">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
          <button key={t} className={`admin-tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="admin-content">
        {tab === "users" && <UsersTab />}
        {tab === "departments" && <DepartmentsTab />}
        {tab === "roles" && <RolesTab />}
        {tab === "datatypes" && <DataTypesTab />}
        {tab === "audit" && <AuditTab />}
        {tab === "system" && <SystemTab />}
      </div>
    </div>
  );
}

// ── shared helpers ─────────────────────────────────────────────────────────────

function PrimaryBtn({ children, disabled, onClick, type = "button" }: {
  children: React.ReactNode; disabled?: boolean;
  onClick?: () => void; type?: "button" | "submit";
}) {
  return (
    <button type={type} className="admin-btn admin-btn-primary" disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

async function apiFetch(url: string, opts: RequestInit = {}) {
  return fetch(url, { credentials: "include", ...opts });
}

// ── Users ─────────────────────────────────────────────────────────────────────

type NewUserForm = { username: string; name: string; password: string; department_id: string; role_id: string };
const EMPTY_USER: NewUserForm = { username: "", name: "", password: "", department_id: "", role_id: "" };

type EditUserForm = { name: string; department_id: string; role_id: string; is_active: number };

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [depts, setDepts] = useState<Department[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [allDocTypes, setAllDocTypes] = useState<DocumentType[]>([]);

  // create form allowed types
  const [createAllowedDtIds, setCreateAllowedDtIds] = useState<string[]>([]);

  // edit row allowed types (keyed by user id)
  const [editAllowedDtIds, setEditAllowedDtIds] = useState<string[]>([]);
  const [editDtLoaded, setEditDtLoaded] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<NewUserForm>(EMPTY_USER);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditUserForm>({ name: "", department_id: "", role_id: "", is_active: 1 });
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  function loadUsers() {
    apiFetch("/api/admin/users").then((r) => r.json())
      .then((d) => { setUsers(Array.isArray(d.items) ? d.items : []); setTotal(d.total ?? 0); })
      .catch(() => {});
  }

  useEffect(() => {
    loadUsers();
    apiFetch("/api/admin/departments").then((r) => r.json())
      .then((d) => { setDepts(Array.isArray(d) ? d.filter((x) => x.status === "active") : []); })
      .catch(() => {});
    apiFetch("/api/admin/roles").then((r) => r.json())
      .then((d) => { setRoles(Array.isArray(d) ? d : []); })
      .catch(() => {});
    apiFetch("/api/admin/doc-types").then((r) => r.json())
      .then((d) => { setAllDocTypes(Array.isArray(d) ? d : []); })
      .catch(() => {});
  }, []);

  // keep form defaults in sync with loaded data
  useEffect(() => {
    if (depts.length > 0 && !form.department_id) setForm((f) => ({ ...f, department_id: depts[0].id }));
  }, [depts]);
  useEffect(() => {
    if (roles.length > 0 && !form.role_id) setForm((f) => ({ ...f, role_id: roles.find((r) => !r.is_system)?.id ?? roles[0].id }));
  }, [roles]);

  async function startEdit(u: AdminUser) {
    setEditingId(u.id);
    setEditForm({ name: u.name, department_id: u.department_id, role_id: u.role_id, is_active: u.is_active });
    setEditError("");
    setEditDtLoaded(false);
    const res = await apiFetch(`/api/admin/users/${u.id}/doc-type-permissions`).catch(() => null);
    if (res && res.ok) {
      const data = await res.json().catch(() => ({}));
      const ids: string[] | null = (data as { allowed_doc_type_ids?: string[] | null }).allowed_doc_type_ids ?? null;
      setEditAllowedDtIds(ids ?? allDocTypes.map((dt) => dt.id));
    } else {
      setEditAllowedDtIds(allDocTypes.map((dt) => dt.id));
    }
    setEditDtLoaded(true);
  }

  function cancelEdit() { setEditingId(null); setEditError(""); setEditDtLoaded(false); }

  async function saveEdit(id: string) {
    setSaving(true); setEditError("");
    try {
      const res = await apiFetch(`/api/admin/users/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editForm),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setEditError((d as { detail?: string }).detail ?? "Save failed.");
        return;
      }
      // Save allowed data types (empty list = all access)
      const isAll = editAllowedDtIds.length === allDocTypes.length;
      await apiFetch(`/api/admin/users/${id}/doc-type-permissions`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_type_ids: isAll ? [] : editAllowedDtIds }),
      }).catch(() => {});
      setEditingId(null);
      setEditDtLoaded(false);
      loadUsers();
    } finally { setSaving(false); }
  }

  async function createUser(e: React.FormEvent) {
    e.preventDefault(); setCreateError("");
    if (!form.username || !form.name || !form.password || !form.department_id || !form.role_id) {
      setCreateError("All fields are required."); return;
    }
    setCreating(true);
    try {
      const res = await apiFetch("/api/admin/users", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      if (res.ok) {
        const created = await res.json().catch(() => ({})) as { id?: string };
        if (created.id && allDocTypes.length > 0) {
          const isAll = createAllowedDtIds.length === allDocTypes.length;
          await apiFetch(`/api/admin/users/${created.id}/doc-type-permissions`, {
            method: "PUT", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ doc_type_ids: isAll ? [] : createAllowedDtIds }),
          }).catch(() => {});
        }
        setForm({ ...EMPTY_USER, department_id: depts[0]?.id ?? "", role_id: roles.find((r) => !r.is_system)?.id ?? "" });
        setCreateAllowedDtIds([]);
        setShowCreate(false); loadUsers();
      } else {
        const d = await res.json().catch(() => ({}));
        setCreateError((d as { detail?: string }).detail ?? "Failed to create user.");
      }
    } finally { setCreating(false); }
  }

  async function deactivate(id: string) {
    if (!confirm("Deactivate this user?")) return;
    await apiFetch(`/api/admin/users/${id}`, { method: "DELETE" });
    loadUsers();
  }

  function toggleDt(id: string, selected: string[], setSelected: (v: string[]) => void) {
    setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }

  async function resetPw(id: string) {
    const pw = prompt("New temporary password (≥ 8 chars):\nThe user will be asked to change it on next login.");
    if (!pw) return;
    const res = await apiFetch(`/api/admin/users/${id}/reset-password`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: pw }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert((d as { detail?: string }).detail ?? "Error");
    } else {
      alert("Password reset. The user will be prompted to set a new password on next login.");
    }
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div>
          <h2 className="admin-section-title">Users</h2>
          <p className="admin-section-sub">{total} total</p>
        </div>
        <PrimaryBtn onClick={() => { setShowCreate((v) => !v); setCreateError(""); }}>
          {showCreate ? "Cancel" : "+ Add user"}
        </PrimaryBtn>
      </div>

      {showCreate && (
        <form className="admin-create-form" onSubmit={createUser}>
          <h3 className="admin-create-title">New user</h3>
          <div className="admin-create-grid">
            <div className="admin-create-field">
              <label>Username</label>
              <input type="text" value={form.username} placeholder="e.g. jsmith"
                onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} />
            </div>
            <div className="admin-create-field">
              <label>Full name</label>
              <input type="text" value={form.name} placeholder="e.g. Jane Smith"
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="admin-create-field">
              <label>Temporary password</label>
              <input type="text" value={form.password} placeholder="Min. 8 characters"
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
            </div>
            <div className="admin-create-field">
              <label>Department</label>
              <select value={form.department_id} onChange={(e) => setForm((f) => ({ ...f, department_id: e.target.value }))}>
                {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div className="admin-create-field">
              <label>Role</label>
              <select value={form.role_id} onChange={(e) => setForm((f) => ({ ...f, role_id: e.target.value }))}>
                {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
          </div>
          {allDocTypes.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Allowed Data Types
              </div>
              <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
                Check the data types this user may see. Leave all unchecked for unrestricted access.
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {allDocTypes.map((dt) => (
                  <label key={dt.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, cursor: "pointer" }}>
                    <input type="checkbox" checked={createAllowedDtIds.includes(dt.id)}
                      onChange={() => toggleDt(dt.id, createAllowedDtIds, setCreateAllowedDtIds)} />
                    <span className="admin-mono" style={{ color: "#94a3b8", fontSize: 12 }}>#{dt.code}</span>
                    <strong>{dt.name}</strong>
                    {dt.description && <span style={{ color: "#94a3b8", fontSize: 12 }}>— {dt.description}</span>}
                  </label>
                ))}
              </div>
            </div>
          )}
          {createError && <div className="admin-create-error">{createError}</div>}
          <div className="admin-create-hint">The user will be asked to change their password on first login.</div>
          <div className="admin-actions" style={{ marginTop: 12 }}>
            <PrimaryBtn type="submit" disabled={creating}>{creating ? "Creating…" : "Create user"}</PrimaryBtn>
            <button type="button" className="admin-btn" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr><th>Username</th><th>Name</th><th>Role</th><th>Department</th><th>Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {users.map((u) =>
              editingId === u.id ? (
                <React.Fragment key={u.id}>
                <tr className="admin-row-editing">
                  <td><span className="admin-mono">{u.username}</span></td>
                  <td>
                    <input className="admin-inline-input" value={editForm.name}
                      onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} />
                  </td>
                  <td>
                    <select className="admin-inline-select" value={editForm.role_id}
                      onChange={(e) => setEditForm((f) => ({ ...f, role_id: e.target.value }))}>
                      {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                  </td>
                  <td>
                    <select className="admin-inline-select" value={editForm.department_id}
                      onChange={(e) => setEditForm((f) => ({ ...f, department_id: e.target.value }))}>
                      {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                  </td>
                  <td>
                    <select className="admin-inline-select" value={editForm.is_active}
                      onChange={(e) => setEditForm((f) => ({ ...f, is_active: Number(e.target.value) }))}>
                      <option value={1}>Active</option>
                      <option value={0}>Inactive</option>
                    </select>
                  </td>
                  <td>
                    {editError && <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 4 }}>{editError}</div>}
                    <div className="admin-actions">
                      <PrimaryBtn disabled={saving} onClick={() => saveEdit(u.id)}>{saving ? "Saving…" : "Save"}</PrimaryBtn>
                      <button className="admin-btn" onClick={cancelEdit}>Cancel</button>
                    </div>
                  </td>
                </tr>
                {allDocTypes.length > 0 && (
                  <tr key={`${u.id}-dt`} className="admin-row-editing">
                    <td colSpan={6} style={{ paddingTop: 0, paddingBottom: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Allowed Data Types
                      </div>
                      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
                        Check the data types this user may see. Leave all unchecked for unrestricted access.
                      </div>
                      {!editDtLoaded ? (
                        <span style={{ fontSize: 13, color: "#94a3b8" }}>Loading…</span>
                      ) : (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px" }}>
                          {allDocTypes.map((dt) => (
                            <label key={dt.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14, cursor: "pointer", minWidth: 180 }}>
                              <input type="checkbox" checked={editAllowedDtIds.includes(dt.id)}
                                onChange={() => toggleDt(dt.id, editAllowedDtIds, setEditAllowedDtIds)} />
                              <span className="admin-mono" style={{ color: "#94a3b8", fontSize: 12 }}>#{dt.code}</span>
                              <strong>{dt.name}</strong>
                            </label>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                </React.Fragment>
              ) : (
                <tr key={u.id} className={u.is_active ? "" : "admin-row-inactive"}>
                  <td>
                    <span className="admin-mono">{u.username}</span>
                    {u.must_change_password ? <span className="admin-badge badge-inactive" style={{ marginLeft: 6 }}>temp pw</span> : null}
                  </td>
                  <td>{u.name}</td>
                  <td>
                    <span className={`admin-badge ${u.role_id === "superadmin" ? "badge-admin" : "badge-member"}`}>
                      {u.role_name}
                    </span>
                  </td>
                  <td>{depts.find((d) => d.id === u.department_id)?.name ?? u.department_id.replace("dept-", "")}</td>
                  <td>
                    <span className={`admin-badge ${u.is_active ? "badge-active" : "badge-inactive"}`}>
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="admin-actions">
                    <button className="admin-btn" onClick={() => startEdit(u)}>Edit</button>
                    <button className="admin-btn" onClick={() => resetPw(u.id)}>Reset pw</button>
                    {u.is_active === 1 && (
                      <button className="admin-btn danger" onClick={() => deactivate(u.id)}>Deactivate</button>
                    )}
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Departments ───────────────────────────────────────────────────────────────

type DeptForm = { name: string; code: string };
const EMPTY_DEPT: DeptForm = { name: "", code: "" };

function DepartmentsTab() {
  const [depts, setDepts] = useState<Department[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<DeptForm>(EMPTY_DEPT);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editStatus, setEditStatus] = useState<"active" | "archived">("active");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  function load() {
    apiFetch("/api/admin/departments").then((r) => r.json())
      .then((d) => setDepts(Array.isArray(d) ? d : []))
      .catch(() => {});
  }
  useEffect(load, []);

  function startEdit(d: Department) {
    setEditingId(d.id); setEditName(d.name); setEditStatus(d.status); setEditError("");
  }
  function cancelEdit() { setEditingId(null); setEditError(""); }

  async function saveEdit(id: string) {
    setSaving(true); setEditError("");
    try {
      const res = await apiFetch(`/api/admin/departments/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editName, status: editStatus }),
      });
      if (res.ok) { setEditingId(null); load(); }
      else { const d = await res.json().catch(() => ({})); setEditError((d as { detail?: string }).detail ?? "Save failed."); }
    } finally { setSaving(false); }
  }

  async function createDept(e: React.FormEvent) {
    e.preventDefault(); setCreateError("");
    if (!form.name || !form.code) { setCreateError("Name and code are required."); return; }
    setCreating(true);
    try {
      const res = await apiFetch("/api/admin/departments", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      if (res.ok) { setForm(EMPTY_DEPT); setShowCreate(false); load(); }
      else { const d = await res.json().catch(() => ({})); setCreateError((d as { detail?: string }).detail ?? "Failed."); }
    } finally { setCreating(false); }
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div>
          <h2 className="admin-section-title">Departments</h2>
          <p className="admin-section-sub">{depts.length} total</p>
        </div>
        <PrimaryBtn onClick={() => { setShowCreate((v) => !v); setCreateError(""); }}>
          {showCreate ? "Cancel" : "+ Add department"}
        </PrimaryBtn>
      </div>

      {showCreate && (
        <form className="admin-create-form" onSubmit={createDept}>
          <h3 className="admin-create-title">New department</h3>
          <div className="admin-create-grid">
            <div className="admin-create-field">
              <label>Name</label>
              <input type="text" value={form.name} placeholder="e.g. Finance"
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="admin-create-field">
              <label>Code (short, uppercase)</label>
              <input type="text" value={form.code} placeholder="e.g. FIN"
                onChange={(e) => setForm((f) => ({ ...f, code: e.target.value.toUpperCase() }))} />
            </div>
          </div>
          {createError && <div className="admin-create-error">{createError}</div>}
          <div className="admin-actions" style={{ marginTop: 12 }}>
            <PrimaryBtn type="submit" disabled={creating}>{creating ? "Creating…" : "Create department"}</PrimaryBtn>
            <button type="button" className="admin-btn" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead><tr><th>Name</th><th>Code</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {depts.map((d) =>
              editingId === d.id ? (
                <tr key={d.id} className="admin-row-editing">
                  <td>
                    <input className="admin-inline-input" value={editName}
                      onChange={(e) => setEditName(e.target.value)} />
                  </td>
                  <td><span className="admin-mono">{d.code}</span></td>
                  <td>
                    <select className="admin-inline-select" value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value as "active" | "archived")}>
                      <option value="active">Active</option>
                      <option value="archived">Archived</option>
                    </select>
                  </td>
                  <td>
                    {editError && <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 4 }}>{editError}</div>}
                    <div className="admin-actions">
                      <PrimaryBtn disabled={saving} onClick={() => saveEdit(d.id)}>{saving ? "Saving…" : "Save"}</PrimaryBtn>
                      <button className="admin-btn" onClick={cancelEdit}>Cancel</button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={d.id}>
                  <td>{d.name}</td>
                  <td><span className="admin-mono">{d.code}</span></td>
                  <td>
                    <span className={`admin-badge ${d.status === "active" ? "badge-active" : "badge-inactive"}`}>
                      {d.status}
                    </span>
                  </td>
                  <td>
                    <button className="admin-btn" onClick={() => startEdit(d)}>Edit</button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Roles ─────────────────────────────────────────────────────────────────────

type RoleForm = { name: string; description: string };
const EMPTY_ROLE: RoleForm = { name: "", description: "" };

function RolesTab() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<RoleForm>(EMPTY_ROLE);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  function load() {
    apiFetch("/api/admin/roles").then((r) => r.json())
      .then((d) => setRoles(Array.isArray(d) ? d : []))
      .catch(() => {});
  }
  useEffect(load, []);

  function startEdit(r: Role) {
    setEditingId(r.id); setEditName(r.name); setEditDesc(r.description); setEditError("");
  }
  function cancelEdit() { setEditingId(null); setEditError(""); }

  async function saveEdit(id: string) {
    setSaving(true); setEditError("");
    try {
      const res = await apiFetch(`/api/admin/roles/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editName, description: editDesc }),
      });
      if (res.ok) { setEditingId(null); load(); }
      else { const d = await res.json().catch(() => ({})); setEditError((d as { detail?: string }).detail ?? "Save failed."); }
    } finally { setSaving(false); }
  }

  async function createRole(e: React.FormEvent) {
    e.preventDefault(); setCreateError("");
    if (!form.name) { setCreateError("Name is required."); return; }
    setCreating(true);
    try {
      const res = await apiFetch("/api/admin/roles", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      if (res.ok) { setForm(EMPTY_ROLE); setShowCreate(false); load(); }
      else { const d = await res.json().catch(() => ({})); setCreateError((d as { detail?: string }).detail ?? "Failed."); }
    } finally { setCreating(false); }
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div>
          <h2 className="admin-section-title">Roles</h2>
          <p className="admin-section-sub">{roles.length} roles</p>
        </div>
        <PrimaryBtn onClick={() => { setShowCreate((v) => !v); setCreateError(""); }}>
          {showCreate ? "Cancel" : "+ Add role"}
        </PrimaryBtn>
      </div>

      {showCreate && (
        <form className="admin-create-form" onSubmit={createRole}>
          <h3 className="admin-create-title">New role</h3>
          <div className="admin-create-grid">
            <div className="admin-create-field">
              <label>Name</label>
              <input type="text" value={form.name} placeholder="e.g. Reviewer"
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="admin-create-field">
              <label>Description</label>
              <input type="text" value={form.description} placeholder="Optional description"
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
            </div>
          </div>
          {createError && <div className="admin-create-error">{createError}</div>}
          <div className="admin-actions" style={{ marginTop: 12 }}>
            <PrimaryBtn type="submit" disabled={creating}>{creating ? "Creating…" : "Create role"}</PrimaryBtn>
            <button type="button" className="admin-btn" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead><tr><th>Name</th><th>Description</th><th>Type</th><th>Permissions</th><th>Actions</th></tr></thead>
          <tbody>
            {roles.map((r) =>
              editingId === r.id ? (
                <tr key={r.id} className="admin-row-editing">
                  <td>
                    <input className="admin-inline-input" value={editName}
                      onChange={(e) => setEditName(e.target.value)} disabled={!!r.is_system} />
                  </td>
                  <td>
                    <input className="admin-inline-input" value={editDesc}
                      onChange={(e) => setEditDesc(e.target.value)} placeholder="Description" />
                  </td>
                  <td>
                    <span className={`admin-badge ${r.is_system ? "badge-admin" : "badge-member"}`}>
                      {r.is_system ? "System" : "Custom"}
                    </span>
                  </td>
                  <td>
                    <div className="admin-perms">
                      {r.permissions.map((p) => <span key={p} className="admin-perm-chip">{p}</span>)}
                    </div>
                  </td>
                  <td>
                    {editError && <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 4 }}>{editError}</div>}
                    <div className="admin-actions">
                      <PrimaryBtn disabled={saving} onClick={() => saveEdit(r.id)}>{saving ? "Saving…" : "Save"}</PrimaryBtn>
                      <button className="admin-btn" onClick={cancelEdit}>Cancel</button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={r.id}>
                  <td><strong>{r.name}</strong></td>
                  <td style={{ color: "#475569", fontSize: 13 }}>{r.description}</td>
                  <td>
                    <span className={`admin-badge ${r.is_system ? "badge-admin" : "badge-member"}`}>
                      {r.is_system ? "System" : "Custom"}
                    </span>
                  </td>
                  <td>
                    <div className="admin-perms">
                      {r.permissions.map((p) => <span key={p} className="admin-perm-chip">{p}</span>)}
                    </div>
                  </td>
                  <td>
                    <button className="admin-btn" onClick={() => startEdit(r)}>Edit</button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Data Types ────────────────────────────────────────────────────────────────

type DtForm = { name: string; description: string };
const EMPTY_DT: DtForm = { name: "", description: "" };

function DataTypesTab() {
  const [types, setTypes] = useState<DocumentType[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<DtForm>(EMPTY_DT);
  const [assignToAll, setAssignToAll] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editStatus, setEditStatus] = useState<"active" | "archived">("active");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  function load() {
    apiFetch("/api/admin/doc-types").then((r) => r.json())
      .then((d) => setTypes(Array.isArray(d) ? d : []))
      .catch(() => {});
  }
  useEffect(load, []);

  function startEdit(dt: DocumentType) {
    setEditingId(dt.id); setEditName(dt.name); setEditDesc(dt.description ?? "");
    setEditStatus(dt.status); setEditError("");
  }
  function cancelEdit() { setEditingId(null); setEditError(""); }

  async function saveEdit(id: string) {
    setSaving(true); setEditError("");
    try {
      const res = await apiFetch(`/api/admin/doc-types/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editName, description: editDesc, status: editStatus }),
      });
      if (res.ok) { setEditingId(null); load(); }
      else { const d = await res.json().catch(() => ({})); setEditError((d as { detail?: string }).detail ?? "Save failed."); }
    } finally { setSaving(false); }
  }

  async function createType(e: React.FormEvent) {
    e.preventDefault(); setCreateError("");
    if (!form.name) { setCreateError("Name is required."); return; }
    setCreating(true);
    try {
      const res = await apiFetch("/api/admin/doc-types", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: form.name, description: form.description }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setCreateError((d as { detail?: string }).detail ?? "Failed.");
        return;
      }
      const created: DocumentType = await res.json();
      // If admin chose to grant this type to all non-admin users, do it now
      if (assignToAll) {
        const usersRes = await apiFetch("/api/admin/users");
        if (usersRes.ok) {
          const allUsers: AdminUser[] = await usersRes.json().catch(() => []);
          const nonAdmins = allUsers.filter((u) => u.role_name !== "admin");
          await Promise.all(nonAdmins.map(async (u) => {
            // Fetch existing permissions then append the new type
            const permRes = await apiFetch(`/api/admin/users/${u.id}/doc-type-permissions`);
            const permData = permRes.ok ? await permRes.json().catch(() => ({})) : {};
            const existing: string[] = (permData as { allowed_doc_type_ids?: string[] | null }).allowed_doc_type_ids ?? [];
            if (!existing.includes(created.id)) {
              await apiFetch(`/api/admin/users/${u.id}/doc-type-permissions`, {
                method: "PUT", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ doc_type_ids: [...existing, created.id] }),
              });
            }
          }));
        }
      }
      setForm(EMPTY_DT); setAssignToAll(false); setShowCreate(false); load();
    } finally { setCreating(false); }
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div>
          <h2 className="admin-section-title">Data Types</h2>
          <p className="admin-section-sub">{types.length} defined — users can only access their allowed types</p>
        </div>
        <PrimaryBtn onClick={() => { setShowCreate((v) => !v); setCreateError(""); }}>
          {showCreate ? "Cancel" : "+ Add data type"}
        </PrimaryBtn>
      </div>

      {showCreate && (
        <form className="admin-create-form" onSubmit={createType}>
          <h3 className="admin-create-title">New data type</h3>
          <div className="admin-create-grid">
            <div className="admin-create-field">
              <label>Name</label>
              <input type="text" value={form.name} placeholder="e.g. Technical Manual"
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="admin-create-field">
              <label>Description (optional)</label>
              <input type="text" value={form.description} placeholder="Brief description of this document category"
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
            </div>
          </div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>Code is assigned automatically as the next unique integer.</div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13, cursor: "pointer", userSelect: "none" }}>
            <input
              type="checkbox"
              checked={assignToAll}
              onChange={(e) => setAssignToAll(e.target.checked)}
              style={{ width: 15, height: 15, accentColor: "#2563eb", cursor: "pointer" }}
            />
            <span>Allen Benutzern (außer Admins) automatisch zuweisen</span>
          </label>
          {createError && <div className="admin-create-error">{createError}</div>}
          <div className="admin-actions" style={{ marginTop: 12 }}>
            <PrimaryBtn type="submit" disabled={creating}>{creating ? "Creating…" : "Create data type"}</PrimaryBtn>
            <button type="button" className="admin-btn" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead><tr><th>#</th><th>Name</th><th>Description</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {types.map((dt) =>
              editingId === dt.id ? (
                <tr key={dt.id} className="admin-row-editing">
                  <td><span className="admin-mono" style={{ color: "#64748b" }}>#{dt.code}</span></td>
                  <td>
                    <input className="admin-inline-input" value={editName}
                      onChange={(e) => setEditName(e.target.value)} />
                  </td>
                  <td>
                    <input className="admin-inline-input" value={editDesc}
                      onChange={(e) => setEditDesc(e.target.value)} placeholder="Description" />
                  </td>
                  <td>
                    <select className="admin-inline-select" value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value as "active" | "archived")}>
                      <option value="active">Active</option>
                      <option value="archived">Archived</option>
                    </select>
                  </td>
                  <td>
                    {editError && <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 4 }}>{editError}</div>}
                    <div className="admin-actions">
                      <PrimaryBtn disabled={saving} onClick={() => saveEdit(dt.id)}>{saving ? "Saving…" : "Save"}</PrimaryBtn>
                      <button className="admin-btn" onClick={cancelEdit}>Cancel</button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={dt.id}>
                  <td><span className="admin-mono" style={{ color: "#64748b" }}>#{dt.code}</span></td>
                  <td><strong>{dt.name}</strong></td>
                  <td style={{ color: "#475569", fontSize: 13 }}>{dt.description}</td>
                  <td>
                    <span className={`admin-badge ${dt.status === "active" ? "badge-active" : "badge-inactive"}`}>
                      {dt.status}
                    </span>
                  </td>
                  <td>
                    <button className="admin-btn" onClick={() => startEdit(dt)}>Edit</button>
                  </td>
                </tr>
              )
            )}
            {types.length === 0 && (
              <tr><td colSpan={5} style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", padding: "24px 0" }}>
                No data types yet. Click "+ Add data type" to define your first category.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Audit Log ─────────────────────────────────────────────────────────────────

function AuditTab() {
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [total, setTotal] = useState(0);
  useEffect(() => {
    apiFetch("/api/admin/audit-log").then((r) => r.json())
      .then((d) => { setRows(Array.isArray(d.items) ? d.items : []); setTotal(d.total ?? 0); })
      .catch(() => {});
  }, []);
  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div>
          <h2 className="admin-section-title">Audit Log</h2>
          <p className="admin-section-sub">{total} events (immutable)</p>
        </div>
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr><th>Time</th><th>User</th><th>Action</th><th>Resource</th><th>Decision</th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><span className="admin-mono" style={{ fontSize: 12 }}>{(r.created_at ?? "").slice(0, 19).replace("T", " ")}</span></td>
                <td>{r.username ?? r.user_id}</td>
                <td>{r.action}</td>
                <td>{r.resource_type ?? ""}</td>
                <td>
                  {r.decision && (
                    <span className={`admin-badge ${r.decision === "deny" ? "badge-deny" : "badge-allow"}`}>
                      {r.decision}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── System ────────────────────────────────────────────────────────────────────

function SystemTab() {
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  useEffect(() => {
    apiFetch("/api/admin/stats").then((r) => r.json())
      .then((d) => setStats(d && typeof d === "object" && !Array.isArray(d) ? d : {}))
      .catch(() => setStats({}));
  }, []);

  if (!stats) return <div className="admin-loading">Loading…</div>;

  const cards = [
    { value: stats.active_users, label: "Active users", icon: "👥" },
    { value: stats.qdrant_point_count?.toLocaleString() ?? "0", label: "Vector chunks", icon: "🧩" },
    { value: `${((stats.storage_bytes ?? 0) / 1024 / 1024).toFixed(1)} MB`, label: "Storage used", icon: "💾" },
  ];

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div>
          <h2 className="admin-section-title">System</h2>
          <p className="admin-section-sub">Live stats</p>
        </div>
      </div>
      <div className="admin-stats-grid">
        {cards.map((c) => (
          <div key={c.label} className="admin-stat-card">
            <div className="stat-icon">{c.icon}</div>
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
