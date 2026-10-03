// Idle sign-out, the visible half (the rule itself lives in apps/accounts/idle.py).
// The first coordinator asked for it on 2026-10-02. A minute before the server signs someone
// out, this says so and offers "I'm still here". It also tells the server about typing and
// tapping it cannot see, so a long request that is still being written is never lost.
// It keeps time by the server's clock (/auth/still-here/ reports the seconds left), because a
// page that reloaded itself on its own clock would count as activity and never sign anyone out.
(function () {
  "use strict";

  // The settings ride on this script's own tag (base.html), read while it runs.
  var me = document.currentScript;
  var body = document.body;
  var limit = me ? parseInt(me.getAttribute("data-idle-seconds"), 10) * 1000 : 0;
  var url = me ? me.getAttribute("data-idle-ping") : null;
  if (!limit || !url) return;

  var WARN_BEFORE = 60 * 1000; // the warning shows one minute before
  var PING_EVERY = 60 * 1000; // typing is reported at most once a minute
  var ASK_EVERY = 20 * 1000; // near the end, ask the server how long is left

  var start = Date.now();
  var deadline = start + limit; // loading this page was activity
  var lastActivity = start;
  var lastPing = start;
  var lastAsk = start;
  var warning = null;

  function check(active) {
    var now = Date.now();
    lastAsk = now;
    if (active) lastPing = now;
    var headers = { Accept: "application/json" };
    if (!active) headers["X-Umi-Background"] = "1";
    fetch(url, { credentials: "same-origin", cache: "no-store", headers: headers })
      .then(function (r) {
        if (r.status !== 200) {
          window.location.reload(); // signed out: the reload lands on sign-in, which says why
          return null;
        }
        return r.json();
      })
      .then(function (data) {
        if (data && typeof data.remaining === "number") deadline = Date.now() + data.remaining * 1000;
      })
      .catch(function () {}); // offline: the next tick tries again
  }

  function hideWarning() {
    if (warning) warning.remove();
    warning = null;
  }

  function showWarning() {
    warning = document.createElement("div");
    warning.setAttribute("role", "alertdialog");
    warning.setAttribute("aria-labelledby", "umi-idle-words");
    warning.style.cssText =
      "position:fixed;left:1rem;right:1rem;top:1rem;z-index:60;max-width:28rem;margin:0 auto;" +
      "background:var(--umi-card,#fff);color:var(--umi-text,#1F1C18);" +
      "border:1px solid var(--umi-border,#E5E1D6);border-radius:1rem;padding:1rem 1.25rem;" +
      "box-shadow:0 12px 32px rgba(31,28,24,0.18);";
    var words = document.createElement("p");
    words.id = "umi-idle-words";
    words.style.cssText = "margin:0 0 0.75rem;font-size:1rem;line-height:1.5;";
    words.textContent = "Still there? To keep your account safe, you will be signed out in 1 minute.";
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn-primary";
    button.textContent = "I'm still here";
    warning.appendChild(words);
    warning.appendChild(button);
    body.appendChild(warning);
    button.focus();
  }

  function touch() {
    var now = Date.now();
    if (warning) {
      // Any tap or key while the warning shows is the answer to it.
      hideWarning();
      lastActivity = now;
      check(true);
      return;
    }
    if (now - lastActivity >= 1000) lastActivity = now;
  }

  ["pointerdown", "keydown", "input", "touchstart"].forEach(function (type) {
    window.addEventListener(type, touch, { capture: true, passive: true });
  });
  window.addEventListener("scroll", touch, { passive: true });
  // A page restored from the back-forward cache has stale timers: ask before trusting them.
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) check(false);
  });

  setInterval(function () {
    var now = Date.now();
    if (lastActivity > lastPing && now - lastPing >= PING_EVERY) {
      check(true);
      return;
    }
    var left = deadline - now;
    if (left <= WARN_BEFORE && now - lastAsk >= ASK_EVERY) {
      check(false); // another tab may have been busy; at zero, the server signs out
      return;
    }
    if (left > WARN_BEFORE) hideWarning();
    else if (left > 0 && !warning) showWarning();
  }, 5000);
})();
