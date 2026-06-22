"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/Badge";
import { Switch } from "@/components/ui/Switch";
import { HealthRow } from "@/components/korpus/HealthRow";
import {
  ShieldCheck,
  Lock,
  ScanSearch,
  ListFilter,
  Brain,
  Database,
  Cpu,
  HardDrive,
  SearchCheck,
  Flag,
  Activity,
  Boxes,
} from "lucide-react";

type ConfigResponse = {
  available_languages?: string[];
  ollama_model?: string;
  top_k?: number;
  embedder_model?: string;
  reranker_model?: string;
};

function SectionHead({ icon, title, tag }: { icon: React.ReactNode; title: string; tag?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 12 }}>
      <span style={{ color: "var(--text-secondary)", display: "inline-flex" }}>{icon}</span>
      <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 600, color: "var(--text-strong)" }}>{title}</h2>
      {tag && (
        <span style={{ marginLeft: "auto", fontSize: "var(--fs-2xs)", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: 5 }}>
          <Lock size={12} color="var(--text-muted)" />{tag}
        </span>
      )}
    </div>
  );
}

export default function SettingsScreen() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [flags, setFlags] = useState([
    { name: "Translated BM25", on: true, desc: "Keyword search across translated text variants." },
    { name: "Sibling expansion", on: true, desc: "Pull adjacent chunks for fuller context." },
    { name: "HyDE", on: false, desc: "Hypothetical-document embeddings for vague queries." },
    { name: "Strict grounding", on: true, desc: "Abstain rather than answer without a verified source." },
  ]);

  useEffect(() => {
    fetch("/api/config", { credentials: "include" })
      .then((r) => r.json())
      .then((data: ConfigResponse) => setConfig(data))
      .catch(() => {});
  }, []);

  const embedder = config?.embedder_model ?? "bge-m3";
  const reranker = config?.reranker_model ?? "bge-reranker-v2-m3";
  const llm = config?.ollama_model ?? "qwen3:8b";

  const MODELS = [
    { role: "Embedder", value: embedder, icon: <ScanSearch size={16} />, note: "multilingual · 1024-dim" },
    { role: "Reranker", value: reranker, icon: <ListFilter size={16} />, note: "cross-encoder" },
    { role: "LLM", value: llm, icon: <Brain size={16} />, note: "via Ollama · q4_K_M" },
  ];

  return (
    <AppShell title="Settings">
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 0 48px" }}>
        {/* Air-gapped banner */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "11px 14px",
          background: "var(--accent-tint)", border: "1px solid var(--accent-700)",
          borderRadius: "var(--r-md)", marginBottom: 22,
        }}>
          <ShieldCheck size={17} color="var(--accent-300)" />
          <span style={{ fontSize: "var(--fs-sm)", color: "var(--accent-100)" }}>
            This deployment is air-gapped. Models and data never leave the host. Configuration is managed by ops via{" "}
            <span style={{ fontFamily: "var(--font-mono)" }}>config.yaml</span>.
          </span>
        </div>

        {/* Model configuration */}
        <section style={{ marginBottom: 28 }}>
          <SectionHead icon={<Boxes size={17} />} title="Model configuration" tag="Read-only · set via config" />
          <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            {MODELS.map((m) => (
              <div key={m.role} style={{
                display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
                background: "var(--surface-card)", border: "1px solid var(--border-default)",
                borderRadius: "var(--r-md)",
              }}>
                <span style={{
                  width: 30, height: 30, borderRadius: "var(--r-sm)",
                  background: "var(--surface-raised)", border: "1px solid var(--border-subtle)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center", flex: "none",
                }}>
                  <span style={{ color: "var(--accent-400)" }}>{m.icon}</span>
                </span>
                <div style={{
                  width: 110, flex: "none", fontSize: "var(--fs-2xs)", fontWeight: 600,
                  letterSpacing: "var(--ls-caps)", textTransform: "uppercase" as const, color: "var(--text-muted)",
                }}>{m.role}</div>
                <div style={{
                  flex: 1, fontFamily: "var(--font-mono)", fontSize: "var(--fs-sm)",
                  color: "var(--text-strong)", fontWeight: 500,
                }}>{m.value}</div>
                <div style={{ fontSize: "var(--fs-xs)", color: "var(--text-muted)" }}>{m.note}</div>
                <Lock size={14} color="var(--text-disabled)" />
              </div>
            ))}
          </div>
        </section>

        {/* Feature flags */}
        <section style={{ marginBottom: 28 }}>
          <SectionHead icon={<Flag size={17} />} title="Feature flags" />
          <div style={{
            border: "1px solid var(--border-default)", borderRadius: "var(--r-md)", overflow: "hidden",
          }}>
            {flags.map((f, i) => (
              <div key={f.name} style={{
                display: "flex", alignItems: "center", gap: 14, padding: "13px 14px",
                background: "var(--surface-card)",
                borderBottom: i < flags.length - 1 ? "1px solid var(--border-subtle)" : "none",
              }}>
                <Switch
                  checked={f.on}
                  onChange={(next) => setFlags((fs) => fs.map((x) => (x.name === f.name ? { ...x, on: next } : x)))}
                  size="sm"
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: "var(--fs-sm)", fontWeight: 600, color: "var(--text-strong)" }}>{f.name}</span>
                    <Badge tone={f.on ? "verify" : "neutral"}>{f.on ? "Enabled" : "Disabled"}</Badge>
                  </div>
                  <div style={{ fontSize: "var(--fs-xs)", color: "var(--text-muted)", marginTop: 2 }}>{f.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* System health */}
        <section style={{ marginBottom: 28 }}>
          <SectionHead icon={<Activity size={17} />} title="System health" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
            <HealthRow service="Qdrant" icon={<Database size={15} />} status="online" detail="1,284 vectors · :6333" />
            <HealthRow service="Ollama" icon={<Cpu size={15} />} status="degraded" detail="llama3.1:8b · :11434" />
            <HealthRow service="Disk" icon={<HardDrive size={15} />} status="online" detail="64% used · 412 GB free" />
            <HealthRow service="Index" icon={<SearchCheck size={15} />} status="online" detail="Last rebuild 4h ago" />
          </div>
        </section>
      </div>
    </AppShell>
  );
}
