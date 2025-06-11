// apps/web/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // You can extend other things here if needed, like fonts,
      // but colors are typically handled via CSS variables in v4.
      fontFamily: {
        mono: [
          "Fira Code",
          "Fira Mono",
          "Menlo",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
}
