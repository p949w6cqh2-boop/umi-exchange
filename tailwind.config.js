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
        // Warm neutral ramp — overrides Tailwind's cool default gray so every
        // gray-* usage across the app reads as warm "parish paper" instead of
        // sterile blue-grey. Lightness preserved (hue → warm), so it's a safe
        // app-wide re-skin with no per-template edits. 900 = ink, 600 = muted.
        gray: {
          50: "#FAF7F1",
          100: "#F1ECE4",
          200: "#E6DED5",
          300: "#D8CEC2",
          400: "#B0A595",
          500: "#8A7F70",
          600: "#6B6358",
          700: "#4A443C",
          800: "#332F29",
          900: "#2C2A29",
        },
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
