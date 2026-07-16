// Variant states (keyed at Stage 5) select via ?v=<name>; default "base".
// Elements declare data-on="state …" (kept only in those states) or
// data-off="state …" (removed in those states). Removal, not hiding — layout stays honest.
const v = new URLSearchParams(location.search).get("v") || "base";
document.documentElement.dataset.v = v;
for (const el of document.querySelectorAll("[data-on]"))
  if (el.dataset.on.split(" ").includes(v))
    el.removeAttribute("data-on"); // stop matching the display:none rule
  else el.remove();
for (const el of document.querySelectorAll("[data-off]"))
  if (el.dataset.off.split(" ").includes(v)) el.remove();
const meta = document.querySelector(".shotmeta");
if (meta && v !== "base") meta.textContent += " · state: " + v;
