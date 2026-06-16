"use client";

import { useState } from "react";

export default function ChangePasswordPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    if (next.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (res.ok) {
        window.location.href = "/";
      } else {
        const d = await res.json().catch(() => ({}));
        setError((d as { detail?: string }).detail ?? "Failed to change password.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="login-title">Set your password</h1>
        <p className="login-subtitle">
          Your account was created with a temporary password. Please set a new one before continuing.
        </p>
        <form className="login-form" onSubmit={submit}>
          <label htmlFor="current">Temporary password</label>
          <input
            id="current"
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
            disabled={loading}
          />
          <label htmlFor="next">New password</label>
          <input
            id="next"
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            required
            disabled={loading}
          />
          <label htmlFor="confirm">Confirm new password</label>
          <input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            required
            disabled={loading}
          />
          {error && <div className="login-error">{error}</div>}
          <button type="submit" disabled={loading || !current || !next || !confirm}>
            {loading ? "Saving…" : "Set new password"}
          </button>
        </form>
      </div>
    </div>
  );
}
