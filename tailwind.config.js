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
        // Parish atmosphere palette.
        parish: {
          bg: "#FDFBF7", // warm off-white paper
          soft: "#F5F0E8", // soft cream
          card: "#FAF7F1", // light warm grey card
          border: "#E6DED5", // subtle warm border
          ink: "#2C2A29", // warm dark brown text
          green: "#2B5E2B", // deep muted green (primary accent)
          greendark: "#244F24", // hover green
          gold: "#C49A3C", // soft gold (secondary accent)
        },
        "umi-primary": "var(--umi-primary, #2B5E2B)",
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
