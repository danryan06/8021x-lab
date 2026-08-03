/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--ink) / <alpha-value>)",
        mist: "rgb(var(--mist) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        signal: "rgb(var(--signal) / <alpha-value>)",
        "signal-ink": "rgb(var(--signal-ink) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        fail: "rgb(var(--fail) / <alpha-value>)",
        header: "rgb(var(--header) / <alpha-value>)",
        "header-fg": "rgb(var(--header-fg) / <alpha-value>)",
        slatepanel: "#1a2430",
      },
      fontFamily: {
        display: ['"IBM Plex Sans"', "Segoe UI", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        soft: "0 10px 30px -18px rgb(var(--shadow) / 0.45)",
      },
    },
  },
  plugins: [],
};
