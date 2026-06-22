"use client";

import React from "react";

type IconButtonVariant = "accent" | "ghost";
type IconButtonSize = "sm" | "md" | "lg";

export interface IconButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: React.ReactNode;
  variant?: IconButtonVariant;
  size?: IconButtonSize;
  active?: boolean;
  label: string;
}

const sizes: Record<IconButtonSize, string> = {
  sm: "var(--control-h-sm)",
  md: "var(--control-h-md)",
  lg: "var(--control-h-lg)",
};

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    {
      icon,
      variant = "ghost",
      size = "md",
      active = false,
      label,
      disabled = false,
      style,
      onMouseEnter,
      onMouseLeave,
      ...rest
    },
    ref
  ) {
    const [hovered, setHovered] = React.useState(false);

    const dimension = sizes[size];

    const variantStyles: React.CSSProperties =
      variant === "accent"
        ? {
            background: active ? "var(--accent)" : "var(--accent-tint)",
            color: active ? "var(--accent-fg)" : "var(--accent)",
          }
        : {
            background: active
              ? "var(--surface-hover)"
              : hovered
              ? "var(--surface-hover)"
              : "transparent",
            color: active ? "var(--text-strong)" : "var(--text-secondary)",
          };

    const hoverOverride: React.CSSProperties =
      !disabled && hovered
        ? variant === "accent"
          ? { background: active ? "var(--accent-hover)" : "var(--accent-tint-strong)" }
          : {}
        : {};

    const baseStyle: React.CSSProperties = {
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      width: dimension,
      height: dimension,
      padding: 0,
      border: "none",
      borderRadius: "var(--r-sm)",
      cursor: disabled ? "not-allowed" : "pointer",
      transition: `all var(--dur-fast) var(--ease-out)`,
      outline: "none",
      opacity: disabled ? 0.5 : 1,
      ...variantStyles,
      ...hoverOverride,
      ...style,
    };

    return (
      <button
        ref={ref}
        type="button"
        aria-label={label}
        disabled={disabled}
        style={baseStyle}
        onMouseEnter={(e) => {
          setHovered(true);
          onMouseEnter?.(e);
        }}
        onMouseLeave={(e) => {
          setHovered(false);
          onMouseLeave?.(e);
        }}
        {...rest}
      >
        {icon}
      </button>
    );
  }
);
