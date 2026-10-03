// Show password: an eye inside every password box. The first coordinator could not check what
// she had typed while creating an account (2026-10-02); the founder chose the familiar eye, with
// a slash through it once the password shows. Screen readers hear "Show password" / "Hide
// password". Without JavaScript the field is an ordinary password field.
(function () {
  "use strict";

  // Feather icons (MIT): "eye" and "eye-off".
  var SVG_OPEN =
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';
  var EYE = SVG_OPEN + '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  var EYE_SLASH =
    SVG_OPEN +
    '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>' +
    '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>' +
    '<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

  var made = 0;

  function show(button, visible) {
    button.innerHTML = visible ? EYE_SLASH : EYE;
    button.setAttribute("aria-label", visible ? "Hide password" : "Show password");
    button.setAttribute("aria-pressed", visible ? "true" : "false");
  }

  function addToggle(input) {
    if (input.dataset.pwToggle) return;
    input.dataset.pwToggle = "1";
    if (!input.id) input.id = "umi-pw-" + made;
    made += 1;

    var wrap = document.createElement("span");
    wrap.className = "umi-pw-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "umi-pw-toggle";
    button.setAttribute("aria-controls", input.id);
    show(button, false);

    button.addEventListener("click", function () {
      var visible = input.type !== "text";
      input.type = visible ? "text" : "password";
      show(button, visible);
    });

    // Hidden again before the form is sent, so the browser files it as a password.
    if (input.form) {
      input.form.addEventListener("submit", function () {
        input.type = "password";
        show(button, false);
      });
    }

    wrap.appendChild(button);
  }

  function scan(root) {
    var fields = root.querySelectorAll('input[type="password"]');
    for (var i = 0; i < fields.length; i++) addToggle(fields[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      scan(document);
    });
  } else {
    scan(document);
  }
  // Forms that HTMX swaps in later get the button too.
  document.addEventListener("htmx:load", function (event) {
    scan(event.target);
  });
})();
