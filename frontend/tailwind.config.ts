import type { Config } from "tailwindcss";

// Artemis's token names, mapped to CSS variables (src/index.css) so the same
// classes give a light reading theme by day and a dark one when Windows is dark.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: v("bg-primary"),
          secondary: v("bg-secondary"),
          surface: v("bg-surface"),
          hover: v("bg-hover"),
          border: v("bg-border"),
        },
        text: {
          primary: v("text-primary"),
          secondary: v("text-secondary"),
          muted: v("text-muted"),
        },
        "on-accent": v("on-accent"),
        accent: {
          brand: v("accent-brand"),
          green: v("accent-green"),
          amber: v("accent-amber"),
          red: v("accent-red"),
          blue: v("accent-blue"),
        },
      },
      fontFamily: {
        sans: ["'Segoe UI Variable Text'", "'Segoe UI'", "system-ui", "-apple-system", "sans-serif"],
        // Cambria has lining figures, so CINs, DINs and amounts in legal text read cleanly.
        serif: ["Cambria", "'Times New Roman'", "serif"],
        mono: ["'Cascadia Mono'", "Consolas", "ui-monospace", "monospace"],
      },
      animation: { "fade-in": "fadeIn 0.15s ease-out" },
      keyframes: { fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } } },
    },
  },
  plugins: [],
} satisfies Config;
