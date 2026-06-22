"use client";

import React from "react";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/Button";

const DEFAULT_MESSAGE =
  "I can't ground this in the documents — try rephrasing, or narrow to a specific document or section.";

export interface AbstainCardProps {
  title?: string;
  message?: string;
  suggestions?: string[];
  onSuggestion?: (s: string) => void;
}

export function AbstainCard({
  title = "Unable to answer",
  message = DEFAULT_MESSAGE,
  suggestions,
  onSuggestion,
}: AbstainCardProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: "var(--sp-5)",
        padding: "var(--sp-7)",
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--r-md)",
      }}
    >
      {/* Icon */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          paddingTop: "var(--sp-1)",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 32,
            height: 32,
            borderRadius: "var(--r-full)",
            background: "var(--accent-tint)",
            color: "var(--accent)",
          }}
        >
          <Info size={18} />
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Title */}
        <div
          style={{
            fontSize: "var(--fs-sm)",
            fontWeight: "var(--fw-semibold)" as unknown as number,
            color: "var(--text-strong)",
            marginBottom: "var(--sp-3)",
          }}
        >
          {title}
        </div>

        {/* Message */}
        <div
          style={{
            fontSize: "var(--fs-sm)",
            lineHeight: "var(--lh-relaxed)",
            color: "var(--text-secondary)",
            marginBottom:
              suggestions && suggestions.length > 0 ? "var(--sp-6)" : undefined,
          }}
        >
          {message}
        </div>

        {/* Suggestions */}
        {suggestions && suggestions.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--sp-3)",
            }}
          >
            {suggestions.map((s) => (
              <Button
                key={s}
                variant="ghost"
                size="sm"
                onClick={() => onSuggestion?.(s)}
                style={{
                  border: "1px solid var(--border-default)",
                }}
              >
                {s}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
