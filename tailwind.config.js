/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./apps/**/*.py"],
  theme: {
    extend: {
      fontFamily: {
        // Warm, friendly body text.
        sans: ["Open Sans", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        // Readable serif for headings — like a parish bulletin.
        serif: ["Lora", "Georgia", "Cambria", "Times New Roman", "serif"],
      },
      colors: {
        // Community Hub atmosphere palette (Direction D: water-teal + gold).
        parish: {
          bg: "#FDFBF7", // warm off-white paper
          soft: "#EFF1EE", // barely-cool soft surface
          card: "#F6F8F5", // barely-cool card
          border: "#DDE6E2", // barely-cool border
          ink: "#2C2A29", // warm dark brown text
          green: "#0F6B73", // water-teal (primary) — name kept for back-compat
          greendark: "#0B585F", // hover teal
          gold: "#C49A3C", // soft gold (secondary accent)
        },
        "umi-primary": "var(--umi-primary, #0F6B73)",
        "umi-primary-hover": "var(--umi-primary-hover, #0B585F)",
        "umi-accent": "var(--umi-accent, #C49A3C)",
      },
      maxWidth: {
        parish: "960px", // intimate, readable content width
      },
      boxShadow: {
        pew: "0 1px 3px rgba(44, 42, 41, 0.06)", // soft, low elevation
      },
    },
  },
  plugins: [],
};
