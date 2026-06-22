"use client";

import React from "react";

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea(
    { invalid = false, style, rows = 4, onFocus, onBlur, ...rest },
    ref
  ) {
    const [focused, setFocused] = React.useState(false);

    const textareaStyle: React.CSSProperties = {
      width: "100%",
      minHeight: "var(--control-h-lg)",
      padding: "var(--sp-4) var(--sp-5)",
      background: "var(--surface-input)",
      color: "var(--text-body)",
      border: `1px solid ${
        invalid
          ? "var(--error)"
          : focused
          ? "var(--border-focus)"
          : "var(--border-default)"
      }`,
      borderRadius: "var(--r-sm)",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--fs-sm)",
      lineHeight: "var(--lh-normal)",
      outline: "none",
      resize: "vertical",
      transition: `border-color var(--dur-fast) var(--ease-out)`,
      boxShadow: focused && !invalid ? "var(--ring)" : "none",
      ...style,
    };

    return (
      <textarea
        ref={ref}
        rows={rows}
        style={textareaStyle}
        onFocus={(e) => {
          setFocused(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          onBlur?.(e);
        }}
        {...rest}
      />
    );
  }
);
