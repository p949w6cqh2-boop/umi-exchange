/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./apps/**/*.py"],
  theme: {
    extend: {
      fontFamily: {
        // Product voice — self-hosted variable grotesk (static/fonts).
        sans: ["Schibsted Grotesk", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        // Editorial display — self-hosted optical-size serif (static/fonts).
        serif: ["Newsreader", "Georgia", "Cambria", "Times New Roman", "serif"],
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
        // "The Commons" palette v2 — stone paper, espresso ink, evergreen.
        parish: {
          bg: "#F6F4EE", // warm stone paper
          soft: "#EDEAE2", // deeper stone (wells/shells)
          card: "#FFFFFF", // true white card
          border: "#E5E1D6", // warm hairline
          ink: "#1F1C18", // espresso ink
          green: "#275D4C", // evergreen (primary) — name kept for back-compat
          greendark: "#1C4739", // hover evergreen
          gold: "#9C7A3C", // muted bronze (offer coding only)
        },
        "umi-primary": "var(--umi-primary, #275D4C)",
        "umi-primary-hover": "var(--umi-primary-hover, #1C4739)",
        "umi-accent": "var(--umi-accent, #9C7A3C)",
      },
      maxWidth: {
        parish: "960px", // intimate, readable content width
      },
      boxShadow: {
        pew: "0 1px 2px rgba(31, 28, 24, 0.05), 0 4px 12px -4px rgba(31, 28, 24, 0.08)", // layered low elevation
        lift: "0 1px 2px rgba(31, 28, 24, 0.05), 0 12px 32px -12px rgba(31, 28, 24, 0.16)",
        deep: "0 2px 4px rgba(31, 28, 24, 0.05), 0 24px 64px -16px rgba(31, 28, 24, 0.22)",
      },
      transitionTimingFunction: {
        physical: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
    },
  },
  plugins: [],
};
