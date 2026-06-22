"use client";

import React from "react";

type ServiceStatus = "online" | "degraded" | "offline";

export interface HealthRowProps {
  service: string;
  status: ServiceStatus;
  statusLabel?: string;
  detail?: string;
  icon?: React.ReactNode;
  style?: React.CSSProperties;
}

const STATUS_CONFIG: Record<ServiceStatus, { color: string; text: string; label: string }> = {
  online: { color: "var(--verify-500)", text: "var(--verify-300)", label: "Online" },
  degraded: { color: "var(--warn-500)", text: "var(--warn-300)", label: "Degraded" },
  offline: { color: "var(--error-500)", text: "var(--error-300)", label: "Offline" },
};

export function HealthRow({ service, status, statusLabel, detail, icon, style }: HealthRowProps) {
  const s = STATUS_CONFIG[status];
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 11, padding: "11px 13px",
      background: "var(--surface-card)", border: "1px solid var(--border-default)",
      borderRadius: "var(--r-md)", ...style,
    }}>
      {icon && (
        <span style={{
          width: 28, height: 28, borderRadius: "var(--r-sm)",
          background: "var(--surface-raised)", border: "1px solid var(--border-subtle)",
          display: "inline-flex", alignItems: "center", justifyContent: "center", flex: "none",
          color: "var(--text-secondary)",
        }}>
          {icon}
        </span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--fs-sm)", fontWeight: 600, color: "var(--text-strong)" }}>{service}</div>
        {detail && <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 1 }}>{detail}</div>}
      </div>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flex: "none" }}>
        <span style={{
          width: 7, height: 7, borderRadius: "var(--r-full)", background: s.color,
          boxShadow: status === "online" ? "0 0 0 3px var(--verify-tint)" : "none",
        }} />
        <span style={{ fontSize: "var(--fs-xs)", fontWeight: 500, color: s.text }}>
          {statusLabel || s.label}
        </span>
      </span>
    </div>
  );
}
