"use client";

import React from "react";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export function Dialog({ open, onClose, title, children, footer }: DialogProps) {
  const dialogRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  React.useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  const overlayStyle: React.CSSProperties = {
    position: "fixed",
    inset: 0,
    background: "var(--surface-overlay)",
    backdropFilter: "blur(6px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: "var(--z-modal)" as unknown as number,
    padding: "var(--sp-6)",
  };

  const dialogStyle: React.CSSProperties = {
    background: "var(--surface-card)",
    border: "1px solid var(--border-default)",
    borderRadius: "var(--r-lg)",
    boxShadow: "var(--shadow-lg)",
    maxWidth: 460,
    width: "100%",
    maxHeight: "85vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  };

  const headerStyle: React.CSSProperties = {
    padding: "var(--sp-6) var(--sp-7)",
    borderBottom: title ? "1px solid var(--border-subtle)" : "none",
  };

  const titleStyle: React.CSSProperties = {
    margin: 0,
    fontSize: "var(--fs-h3)",
    fontWeight: "var(--fw-semibold)" as unknown as number,
    color: "var(--text-strong)",
    lineHeight: "var(--lh-tight)",
  };

  const bodyStyle: React.CSSProperties = {
    padding: "var(--sp-6) var(--sp-7)",
    overflowY: "auto",
    flex: 1,
  };

  const footerStyle: React.CSSProperties = {
    padding: "var(--sp-5) var(--sp-7)",
    borderTop: "1px solid var(--border-subtle)",
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: "var(--sp-4)",
  };

  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }

  return (
    <div style={overlayStyle} onClick={handleOverlayClick} role="presentation">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title || "Dialog"}
        style={dialogStyle}
      >
        {title && (
          <div style={headerStyle}>
            <h2 style={titleStyle}>{title}</h2>
          </div>
        )}
        <div style={bodyStyle}>{children}</div>
        {footer && <div style={footerStyle}>{footer}</div>}
      </div>
    </div>
  );
}
