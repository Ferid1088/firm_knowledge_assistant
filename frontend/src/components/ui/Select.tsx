"use client";

import React from "react";

export interface SelectOption {
  label: string;
  value: string;
}

export interface SelectProps
  extends Omit<
    React.SelectHTMLAttributes<HTMLSelectElement>,
    "onChange" | "value"
  > {
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  function Select(
    { options, value, onChange, placeholder, style, onFocus, onBlur, ...rest },
    ref
  ) {
    const [focused, setFocused] = React.useState(false);

    const wrapperStyle: React.CSSProperties = {
      position: "relative",
      display: "inline-flex",
      width: "100%",
    };

    const selectStyle: React.CSSProperties = {
      width: "100%",
      height: "var(--control-h-md)",
      padding: "0 var(--sp-8) 0 var(--sp-5)",
      background: "var(--surface-input)",
      color: value ? "var(--text-body)" : "var(--text-muted)",
      border: `1px solid ${
        focused ? "var(--border-focus)" : "var(--border-default)"
      }`,
      borderRadius: "var(--r-sm)",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--fs-sm)",
      lineHeight: 1,
      cursor: "pointer",
      outline: "none",
      appearance: "none",
      transition: `border-color var(--dur-fast) var(--ease-out)`,
      boxShadow: focused ? "var(--ring)" : "none",
      ...style,
    };

    const chevronStyle: React.CSSProperties = {
      position: "absolute",
      right: "var(--sp-4)",
      top: "50%",
      transform: "translateY(-50%)",
      pointerEvents: "none",
      color: "var(--text-muted)",
      display: "inline-flex",
    };

    return (
      <div style={wrapperStyle}>
        <select
          ref={ref}
          value={value}
          style={selectStyle}
          onChange={(e) => onChange(e.target.value)}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          {...rest}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <span style={chevronStyle}>
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 4.5L6 7.5L9 4.5" />
          </svg>
        </span>
      </div>
    );
  }
);
