"use client";

import React from "react";

type InputSize = "sm" | "md" | "lg";

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  iconLeft?: React.ReactNode;
  invalid?: boolean;
  size?: InputSize;
  mono?: boolean;
}

const heights: Record<InputSize, string> = {
  sm: "var(--control-h-sm)",
  md: "var(--control-h-md)",
  lg: "var(--control-h-lg)",
};

const fontSizes: Record<InputSize, string> = {
  sm: "var(--fs-xs)",
  md: "var(--fs-sm)",
  lg: "var(--fs-body)",
};

const iconPaddings: Record<InputSize, string> = {
  sm: "var(--sp-8)",
  md: "var(--sp-9)",
  lg: "var(--sp-10)",
};

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input(
    {
      iconLeft,
      invalid = false,
      size = "md",
      mono = false,
      style,
      onFocus,
      onBlur,
      ...rest
    },
    ref
  ) {
    const [focused, setFocused] = React.useState(false);

    const wrapperStyle: React.CSSProperties = {
      position: "relative",
      display: "inline-flex",
      alignItems: "center",
      width: "100%",
    };

    const iconStyle: React.CSSProperties = {
      position: "absolute",
      left: "var(--sp-4)",
      display: "inline-flex",
      color: "var(--text-muted)",
      pointerEvents: "none",
    };

    const inputStyle: React.CSSProperties = {
      width: "100%",
      height: heights[size],
      padding: iconLeft
        ? `0 var(--sp-5) 0 ${iconPaddings[size]}`
        : "0 var(--sp-5)",
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
      fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
      fontSize: fontSizes[size],
      lineHeight: 1,
      outline: "none",
      transition: `border-color var(--dur-fast) var(--ease-out)`,
      boxShadow: focused && !invalid ? "var(--ring)" : "none",
      ...style,
    };

    return (
      <div style={wrapperStyle}>
        {iconLeft && <span style={iconStyle}>{iconLeft}</span>}
        <input
          ref={ref}
          style={inputStyle}
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
      </div>
    );
  }
);
