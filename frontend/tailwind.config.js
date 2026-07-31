/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f1720",
        slatepanel: "#1a2430",
        signal: "#3d9b8f",
        warn: "#d97706",
        fail: "#dc2626",
        mist: "#e8eef2",
      },
      fontFamily: {
        display: ["\"IBM Plex Sans\"", "Segoe UI", "sans-serif"],
        mono: ["\"IBM Plex Mono\"", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
