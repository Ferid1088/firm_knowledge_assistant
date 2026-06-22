"use client";

import React from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  MessageSquare,
  Upload,
  Settings,
  Sun,
  Moon,
  HelpCircle,
  ShieldCheck,
} from "lucide-react";
import { useTheme } from "@/lib/theme";
import { IconButton } from "@/components/ui/IconButton";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { LanguagePicker } from "@/components/korpus/LanguagePicker";

interface NavItem {
  href: string;
  icon: React.ReactNode;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", icon: <MessageSquare size={20} />, label: "Chat" },
  { href: "/ingest", icon: <Upload size={20} />, label: "Ingest" },
  { href: "/settings", icon: <Settings size={20} />, label: "Settings" },
];

const DEFAULT_LANGUAGES = [
  { code: "de", label: "Deutsch", locked: true },
  { code: "en", label: "English" },
  { code: "fr", label: "Francais" },
];

export interface AppShellProps {
  title: string;
  /** When true, removes padding from the content area (for full-bleed layouts). */
  flush?: boolean;
  onHelp?: () => void;
  children: React.ReactNode;
}

export function AppShell({ title, flush = false, onHelp, children }: AppShellProps) {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  const [activeLangs, setActiveLangs] = React.useState<string[]>(["de"]);

  const handleLangToggle = React.useCallback((code: string) => {
    if (code === "de") return;
    setActiveLangs((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  }, []);

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
        background: "var(--bg-app)",
      }}
    >
      {/* Left nav rail */}
      <nav
        style={{
          width: "var(--rail-nav)",
          minWidth: "var(--rail-nav)",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          background: "var(--bg-panel)",
          borderRight: "1px solid var(--border-subtle)",
          paddingTop: "var(--sp-6)",
          paddingBottom: "var(--sp-6)",
          zIndex: "var(--z-sticky)",
        }}
      >
        {/* Top: mark */}
        <Link
          href="/"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "var(--sp-9)",
            textDecoration: "none",
          }}
        >
          <img
            src="/korpus-mark.svg"
            alt="Korpus"
            width={28}
            height={28}
            style={{ display: "block" }}
          />
        </Link>

        {/* Middle: nav items */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "var(--sp-2)",
            flex: 1,
          }}
        >
          {NAV_ITEMS.map((item) => {
            const isActive = item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                style={{ textDecoration: "none", position: "relative" }}
              >
                {isActive && (
                  <span
                    style={{
                      position: "absolute",
                      left: -8,
                      top: "50%",
                      transform: "translateY(-50%)",
                      width: 3,
                      height: 20,
                      borderRadius: "var(--r-full)",
                      background: "var(--accent)",
                    }}
                  />
                )}
                <IconButton
                  icon={item.icon}
                  label={item.label}
                  active={isActive}
                  variant="ghost"
                  size="md"
                  style={{ pointerEvents: "none" }}
                />
              </Link>
            );
          })}
        </div>

        {/* Bottom: theme toggle + avatar */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "var(--sp-4)",
          }}
        >
          <IconButton
            icon={theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            variant="ghost"
            size="sm"
            onClick={toggle}
          />
          <Avatar name="Korpus User" size="sm" />
        </div>
      </nav>

      {/* Right area */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          height: "100%",
        }}
      >
        {/* Top bar */}
        <header
          style={{
            height: "var(--header-h)",
            minHeight: "var(--header-h)",
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-5)",
            padding: "0 var(--sp-8)",
            background: "var(--bg-panel)",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-4)" }}>
            <h3
              style={{
                margin: 0,
                fontSize: "var(--fs-h3)",
                fontWeight: "var(--fw-semibold)" as unknown as number,
                color: "var(--text-strong)",
                lineHeight: "var(--lh-tight)",
              }}
            >
              {title}
            </h3>
            <Badge tone="accent" style={{ display: "inline-flex", alignItems: "center", gap: "var(--sp-2)" }}>
              <ShieldCheck size={12} />
              Air-gapped
            </Badge>
          </div>

          <div style={{ flex: 1 }} />

          <LanguagePicker
            languages={DEFAULT_LANGUAGES}
            active={activeLangs}
            onToggle={handleLangToggle}
          />

          <IconButton
            icon={<HelpCircle size={18} />}
            label="Help"
            variant="ghost"
            size="sm"
            onClick={onHelp}
          />
        </header>

        {/* Content */}
        <main
          style={{
            flex: 1,
            overflow: flush ? "hidden" : "auto",
            padding: flush ? 0 : "var(--sp-8)",
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
