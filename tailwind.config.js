/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./apps/**/*.py"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Open Sans", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
      },
      colors: {
        "umi-primary": "var(--umi-primary, #1A1A2E)",
        "umi-accent": "var(--umi-accent, #3B82F6)",
      },
    },
  },
  plugins: [],
};
