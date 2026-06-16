"use client";

import { useEffect, useState } from "react";
import type { AdminUser, Department, Role } from "@/lib/types";

type Tab = "users" | "departments" | "roles" | "audit" | "system";

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");

  return (
    <div className="admin-page">
      <div className="admin-header">
        <span>⚙ Admin Panel</span>
        <a href="/" className="admin-back">← Back to chat</a>
      </div>
      <div className="admin-tabs">
        {(["users", "departments", "roles", "audit", "system"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`admin-tab${tab === t ? " active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      <div className="admin-content">
        {tab === "users" && <UsersTab />}
        {tab === "departments" && <DepartmentsTab />}
        {tab === "roles" && <RolesTab />}
        {tab === "audit" && <AuditTab />}
        {tab === "system" && <SystemTab />}
      </div>
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);

  function load() {
    fetch("/api/admin/users", { credentials: "include" })
      .then((r) => r.json())
      .then((d) => { setUsers(d.items ?? []); setTotal(d.total ?? 0); });
  }
  useEffect(load, []);

  async function deactivate(id: string) {
    if (!confirm("Deactivate this user?")) return;
    await fetch(`/api/admin/users/${id}`, { method: "DELETE", credentials: "include" });
    load();
  }

  async function resetPw(id: string) {
    const pw = prompt("New password (≥ 8 chars):");
    if (!pw) return;
    const res = await fetch(`/api/admin/users/${id}/reset-password`, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: pw }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert((d as { detail?: string }).detail ?? "Error");
    }
  }

  return (
    <div>
      <div className="admin-section-header">
        <h2>Users ({total})</h2>
      </div>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Username</th><th>Name</th><th>Role</th><th>Department</th><th>Active</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
              <td>{u.username}</td>
              <td>{u.name}</td>
              <td>{u.role_name}</td>
              <td>{u.department_id}</td>
              <td>{u.is_active ? "✓" : "✗"}</td>
              <td>
                <button className="admin-action-btn" onClick={() => resetPw(u.id)}>Reset pw</button>
                {u.is_active === 1 && (
                  <button className="admin-action-btn danger" onClick={() => deactivate(u.id)}>Deactivate</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DepartmentsTab() {
  const [depts, setDepts] = useState<Department[]>([]);
  useEffect(() => {
    fetch("/api/admin/departments", { credentials: "include" }).then((r) => r.json()).then(setDepts);
  }, []);
  return (
    <div>
      <h2>Departments</h2>
      <table className="admin-table">
        <thead><tr><th>Name</th><th>Code</th><th>Status</th></tr></thead>
        <tbody>
          {depts.map((d) => (
            <tr key={d.id}><td>{d.name}</td><td>{d.code}</td><td>{d.status}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RolesTab() {
  const [roles, setRoles] = useState<Role[]>([]);
  useEffect(() => {
    fetch("/api/admin/roles", { credentials: "include" }).then((r) => r.json()).then(setRoles);
  }, []);
  return (
    <div>
      <h2>Roles</h2>
      <table className="admin-table">
        <thead><tr><th>Name</th><th>System</th><th>Permissions</th></tr></thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td>{r.is_system ? "✓" : ""}</td>
              <td style={{ fontSize: 12 }}>{r.permissions.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditTab() {
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [total, setTotal] = useState(0);
  useEffect(() => {
    fetch("/api/admin/audit-log", { credentials: "include" })
      .then((r) => r.json())
      .then((d) => { setRows(d.items ?? []); setTotal(d.total ?? 0); });
  }, []);
  return (
    <div>
      <h2>Audit Log ({total})</h2>
      <table className="admin-table">
        <thead>
          <tr><th>Time</th><th>User</th><th>Action</th><th>Resource</th><th>Decision</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={{ fontSize: 12 }}>{(r.created_at ?? "").slice(0, 19).replace("T", " ")}</td>
              <td>{r.username ?? r.user_id}</td>
              <td>{r.action}</td>
              <td>{r.resource_type ?? ""}</td>
              <td style={{ color: r.decision === "deny" ? "#991b1b" : "#166534" }}>{r.decision ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SystemTab() {
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  useEffect(() => {
    fetch("/api/admin/stats", { credentials: "include" }).then((r) => r.json()).then(setStats);
  }, []);
  if (!stats) return <p>Loading…</p>;
  return (
    <div>
      <h2>System</h2>
      <div className="admin-stats-grid">
        <div className="admin-stat-card">
          <div className="stat-value">{stats.active_users}</div>
          <div className="stat-label">Active users</div>
        </div>
        <div className="admin-stat-card">
          <div className="stat-value">{stats.qdrant_point_count}</div>
          <div className="stat-label">Vector chunks</div>
        </div>
        <div className="admin-stat-card">
          <div className="stat-value">{((stats.storage_bytes ?? 0) / 1024 / 1024).toFixed(1)} MB</div>
          <div className="stat-label">Storage</div>
        </div>
      </div>
    </div>
  );
}
