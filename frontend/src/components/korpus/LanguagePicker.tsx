"use client";

import React from "react";
import { ChevronDown, Globe } from "lucide-react";

interface Language {
  code: string;
  label: string;
  locked?: boolean;
}

export interface LanguagePickerProps {
  languages: Language[];
  active: string[];
  onToggle: (code: string) => void;
}

export function LanguagePicker({ languages, active, onToggle }: LanguagePickerProps) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  // Close on outside click
  React.useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--sp-3)",
          height: "var(--control-h-sm)",
          padding: "0 var(--sp-4)",
          background: "var(--surface-raised)",
          border: "1px solid var(--border-default)",
          borderRadius: "var(--r-sm)",
          color: "var(--text-body)",
          fontSize: "var(--fs-sm)",
          fontFamily: "var(--font-sans)",
          fontWeight: "var(--fw-medium)" as unknown as number,
          cursor: "pointer",
          transition: `all var(--dur-fast) var(--ease-out)`,
          outline: "none",
        }}
      >
        <Globe size={14} style={{ color: "var(--text-secondary)" }} />

        {/* Active language badges */}
        <span style={{ display: "inline-flex", gap: "var(--sp-2)" }}>
          {active.map((code) => (
            <span
              key={code}
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                height: 18,
                padding: "0 var(--sp-2)",
                borderRadius: "var(--r-xs)",
                background:
                  code === "de" ? "var(--accent-tint-strong)" : "var(--surface-hover)",
                color: code === "de" ? "var(--accent)" : "var(--text-body)",
                fontSize: "var(--fs-2xs)",
                fontWeight: "var(--fw-semibold)" as unknown as number,
                textTransform: "uppercase",
                letterSpacing: "var(--ls-caps)",
              }}
            >
              {code}
            </span>
          ))}
        </span>

        <ChevronDown
          size={14}
          style={{
            color: "var(--text-muted)",
            transition: `transform var(--dur-fast) var(--ease-out)`,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + var(--sp-2))",
            right: 0,
            minWidth: 200,
            background: "var(--surface-card)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--r-md)",
            boxShadow: "var(--shadow-pop)",
            padding: "var(--sp-3)",
            zIndex: "var(--z-dropdown)",
          }}
        >
          <div
            style={{
              padding: "var(--sp-3) var(--sp-4)",
              fontSize: "var(--fs-xs)",
              fontWeight: "var(--fw-semibold)" as unknown as number,
              letterSpacing: "var(--ls-caps)",
              textTransform: "uppercase",
              color: "var(--text-secondary)",
            }}
          >
            Search languages
          </div>

          {languages.map((lang) => {
            const isActive = active.includes(lang.code);
            const isLocked = !!lang.locked;

            return (
              <button
                key={lang.code}
                type="button"
                disabled={isLocked}
                onClick={() => onToggle(lang.code)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-4)",
                  width: "100%",
                  padding: "var(--sp-3) var(--sp-4)",
                  background: "transparent",
                  border: "none",
                  borderRadius: "var(--r-sm)",
                  cursor: isLocked ? "default" : "pointer",
                  fontFamily: "var(--font-sans)",
                  fontSize: "var(--fs-sm)",
                  color: "var(--text-body)",
                  textAlign: "left",
                  transition: `background var(--dur-fast) var(--ease-out)`,
                  outline: "none",
                  opacity: isLocked ? 0.7 : 1,
                }}
                onMouseEnter={(e) => {
                  if (!isLocked)
                    (e.currentTarget as HTMLElement).style.background =
                      "var(--surface-hover)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = "transparent";
                }}
              >
                {/* Checkbox */}
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 16,
                    height: 16,
                    borderRadius: "var(--r-xs)",
                    border: isActive
                      ? "1.5px solid var(--accent)"
                      : "1.5px solid var(--border-strong)",
                    background: isActive ? "var(--accent)" : "transparent",
                    transition: `all var(--dur-fast) var(--ease-out)`,
                    flexShrink: 0,
                  }}
                >
                  {isActive && (
                    <svg
                      width="10"
                      height="8"
                      viewBox="0 0 10 8"
                      fill="none"
                      style={{ display: "block" }}
                    >
                      <path
                        d="M1 4L3.5 6.5L9 1"
                        stroke="var(--accent-fg)"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </span>

                {/* Code badge */}
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 28,
                    height: 18,
                    borderRadius: "var(--r-xs)",
                    background: "var(--surface-raised)",
                    fontSize: "var(--fs-2xs)",
                    fontWeight: "var(--fw-semibold)" as unknown as number,
                    textTransform: "uppercase",
                    letterSpacing: "var(--ls-caps)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {lang.code}
                </span>

                {/* Label */}
                <span style={{ flex: 1 }}>{lang.label}</span>

                {/* Lock indicator */}
                {isLocked && (
                  <span
                    style={{
                      fontSize: "var(--fs-2xs)",
                      color: "var(--text-muted)",
                      fontStyle: "italic",
                    }}
                  >
                    always on
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
