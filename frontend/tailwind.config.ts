import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        app: "var(--bg-app)",
        panel: "var(--bg-panel)",
        card: "var(--surface-card)",
        raised: "var(--surface-raised)",
        "surface-hover": "var(--surface-hover)",
        input: "var(--surface-input)",
        strong: "var(--text-strong)",
        body: "var(--text-body)",
        secondary: "var(--text-secondary)",
        muted: "var(--text-muted)",
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          press: "var(--accent-press)",
          fg: "var(--accent-fg)",
          tint: "var(--accent-tint)",
          "tint-strong": "var(--accent-tint-strong)",
        },
        verify: {
          DEFAULT: "var(--verify)",
          tint: "var(--verify-tint)",
        },
        warn: {
          DEFAULT: "var(--warn)",
          tint: "var(--warn-tint)",
        },
        error: {
          DEFAULT: "var(--error)",
          tint: "var(--error-tint)",
        },
      },
      borderColor: {
        subtle: "var(--border-subtle)",
        DEFAULT: "var(--border-default)",
        strong: "var(--border-strong)",
        focus: "var(--border-focus)",
      },
      fontFamily: {
        sans: "var(--font-sans)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        display: "var(--fs-display)",
        h1: "var(--fs-h1)",
        h2: "var(--fs-h2)",
        h3: "var(--fs-h3)",
        body: "var(--fs-body)",
        sm: "var(--fs-sm)",
        xs: "var(--fs-xs)",
        "2xs": "var(--fs-2xs)",
      },
      borderRadius: {
        xs: "var(--r-xs)",
        sm: "var(--r-sm)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
        full: "var(--r-full)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        pop: "var(--shadow-pop)",
      },
      transitionTimingFunction: {
        out: "var(--ease-out)",
        "in-out": "var(--ease-in-out)",
      },
    },
  },
  plugins: [],
};

export default config;
