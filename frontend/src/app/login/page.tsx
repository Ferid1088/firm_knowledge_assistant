"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import {
  User,
  Lock,
  ArrowRight,
  ShieldCheck,
  KeyRound,
} from "lucide-react";

const DEPARTMENTS = [
  { label: "Engineering", value: "engineering" },
  { label: "Product", value: "product" },
  { label: "Legal", value: "legal" },
  { label: "Finance", value: "finance" },
  { label: "Operations", value: "operations" },
];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [department, setDepartment] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      router.replace("/");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      if (msg.includes("429") || msg.toLowerCase().includes("too many")) {
        setError("Too many attempts. Try again in 15 minutes.");
      } else {
        setError("Invalid credentials");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        width: "100%",
        background: "var(--bg-app)",
      }}
    >
      {/* ── Left brand panel ──────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          width: "50%",
          maxWidth: 640,
          padding: "var(--sp-10) var(--sp-10) var(--sp-9)",
          background: "var(--bg-panel)",
          borderRight: "1px solid var(--border-subtle)",
        }}
        className="login-brand-panel"
      >
        <div>
          {/* Wordmark */}
          <img
            src="/korpus-wordmark.svg"
            alt="Korpus"
            width={134}
            height={32}
            style={{ display: "block", marginBottom: "var(--sp-10)" }}
          />

          {/* Headline */}
          <h1
            style={{
              margin: 0,
              fontSize: "var(--fs-display)",
              fontWeight: "var(--fw-bold)" as unknown as number,
              lineHeight: "var(--lh-tight)",
              letterSpacing: "var(--ls-tight)",
              color: "var(--text-strong)",
              maxWidth: "16ch",
            }}
          >
            Grounded answers from your own documents.
          </h1>

          {/* Description */}
          <p
            style={{
              marginTop: "var(--sp-7)",
              marginBottom: 0,
              fontSize: "var(--fs-body)",
              lineHeight: "var(--lh-relaxed)",
              color: "var(--text-secondary)",
              maxWidth: "42ch",
            }}
          >
            Korpus retrieves, verifies, and cites from your internal document
            base — fully air-gapped, nothing leaves your network.
          </p>

          {/* Feature pills */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--sp-3)",
              marginTop: "var(--sp-8)",
            }}
          >
            {["Air-gapped", "Verified citations", "DE · EN"].map(
              (label) => (
                <span
                  key={label}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "var(--sp-2)",
                    padding: "var(--sp-2) var(--sp-5)",
                    borderRadius: "var(--r-full)",
                    background: "var(--accent-tint)",
                    border: "1px solid var(--border-subtle)",
                    fontSize: "var(--fs-xs)",
                    fontWeight: "var(--fw-medium)" as unknown as number,
                    color: "var(--text-body)",
                    letterSpacing: "var(--ls-wide)",
                  }}
                >
                  {label}
                </span>
              )
            )}
          </div>
        </div>

        {/* Build version footer */}
        <p
          style={{
            margin: 0,
            fontSize: "var(--fs-2xs)",
            color: "var(--text-muted)",
            letterSpacing: "var(--ls-wide)",
          }}
        >
          Korpus v0.1.0-pilot &middot; Air-gapped deployment
        </p>
      </div>

      {/* ── Right form panel ─────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "var(--sp-8)",
          background: "var(--bg-app)",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 400,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Mark logo */}
          <div style={{ marginBottom: "var(--sp-9)" }}>
            <img
              src="/korpus-mark.svg"
              alt="Korpus"
              width={40}
              height={40}
              style={{ display: "block" }}
            />
          </div>

          {/* Heading */}
          <h2
            style={{
              margin: 0,
              fontSize: "var(--fs-h1)",
              fontWeight: "var(--fw-bold)" as unknown as number,
              color: "var(--text-strong)",
              lineHeight: "var(--lh-tight)",
            }}
          >
            Sign in
          </h2>
          <p
            style={{
              margin: 0,
              marginTop: "var(--sp-2)",
              fontSize: "var(--fs-sm)",
              color: "var(--text-secondary)",
              lineHeight: "var(--lh-normal)",
            }}
          >
            Use your company directory credentials
          </p>

          {/* Form */}
          <form
            onSubmit={handleSubmit}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-5)",
              marginTop: "var(--sp-8)",
            }}
          >
            {/* Username */}
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
              <label
                htmlFor="username"
                style={{
                  fontSize: "var(--fs-xs)",
                  fontWeight: "var(--fw-medium)" as unknown as number,
                  color: "var(--text-secondary)",
                  letterSpacing: "var(--ls-caps)",
                  textTransform: "uppercase",
                }}
              >
                Username
              </label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                disabled={loading}
                placeholder="e.g. jdoe"
                size="lg"
                mono
                iconLeft={<User size={16} />}
              />
            </div>

            {/* Password */}
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
              <label
                htmlFor="password"
                style={{
                  fontSize: "var(--fs-xs)",
                  fontWeight: "var(--fw-medium)" as unknown as number,
                  color: "var(--text-secondary)",
                  letterSpacing: "var(--ls-caps)",
                  textTransform: "uppercase",
                }}
              >
                Password
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                disabled={loading}
                placeholder="••••••••"
                size="lg"
                iconLeft={<Lock size={16} />}
              />
            </div>

            {/* Department */}
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
              <label
                htmlFor="department"
                style={{
                  fontSize: "var(--fs-xs)",
                  fontWeight: "var(--fw-medium)" as unknown as number,
                  color: "var(--text-secondary)",
                  letterSpacing: "var(--ls-caps)",
                  textTransform: "uppercase",
                }}
              >
                Department
              </label>
              <Select
                value={department}
                onChange={setDepartment}
                options={DEPARTMENTS}
                placeholder="Select department"
              />
            </div>

            {/* Keep me signed in */}
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-3)",
                cursor: "pointer",
                fontSize: "var(--fs-sm)",
                color: "var(--text-body)",
                userSelect: "none",
              }}
            >
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                style={{
                  width: 16,
                  height: 16,
                  accentColor: "var(--accent)",
                  cursor: "pointer",
                  borderRadius: "var(--r-xs)",
                }}
              />
              Keep me signed in
            </label>

            {/* Error */}
            {error && (
              <div
                role="alert"
                style={{
                  padding: "var(--sp-4) var(--sp-5)",
                  borderRadius: "var(--r-sm)",
                  background: "var(--error-tint)",
                  border: "1px solid var(--error-300)",
                  color: "var(--error-300)",
                  fontSize: "var(--fs-sm)",
                  fontWeight: "var(--fw-medium)" as unknown as number,
                }}
              >
                {error}
              </div>
            )}

            {/* Sign in button */}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              disabled={loading || !username || !password}
              iconRight={!loading ? <ArrowRight size={18} /> : undefined}
              style={{ marginTop: "var(--sp-2)" }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          {/* OR divider */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-5)",
              margin: "var(--sp-7) 0",
            }}
          >
            <div
              style={{
                flex: 1,
                height: 1,
                background: "var(--border-subtle)",
              }}
            />
            <span
              style={{
                fontSize: "var(--fs-xs)",
                color: "var(--text-muted)",
                fontWeight: "var(--fw-medium)" as unknown as number,
                textTransform: "uppercase",
                letterSpacing: "var(--ls-caps)",
              }}
            >
              OR
            </span>
            <div
              style={{
                flex: 1,
                height: 1,
                background: "var(--border-subtle)",
              }}
            />
          </div>

          {/* SSO button */}
          <Button
            type="button"
            variant="secondary"
            size="lg"
            fullWidth
            iconLeft={<KeyRound size={18} />}
          >
            Continue with SSO
          </Button>

          {/* Air-gapped note */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-3)",
              marginTop: "var(--sp-8)",
              padding: "var(--sp-4) var(--sp-5)",
              borderRadius: "var(--r-sm)",
              background: "var(--surface-card)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <ShieldCheck
              size={16}
              style={{ color: "var(--verify)", flexShrink: 0 }}
            />
            <span
              style={{
                fontSize: "var(--fs-xs)",
                color: "var(--text-muted)",
                lineHeight: "var(--lh-snug)",
              }}
            >
              Air-gapped deployment — credentials are verified against your
              internal directory. No data leaves the network.
            </span>
          </div>
        </div>
      </div>

      {/* ── Responsive: hide brand panel on small screens ──── */}
      <style>{`
        .login-brand-panel {
          display: flex;
        }
        @media (max-width: 880px) {
          .login-brand-panel {
            display: none !important;
          }
        }
      `}</style>
    </div>
  );
}
