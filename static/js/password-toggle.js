// Show password: every password field gets a plain "Show password" button under it.
// The first coordinator could not check what she had typed while creating an account
// (2026-10-02). Words, not an eye icon, because the people she helps do not read icons.
// Progressive enhancement: without JavaScript the field is an ordinary password field.
(function () {
  "use strict";

  var made = 0;

  function addToggle(input) {
    if (input.dataset.pwToggle) return;
    input.dataset.pwToggle = "1";
    if (!input.id) input.id = "umi-pw-" + made;
    made += 1;

    var button = document.createElement("button");
    button.type = "button";
    button.className = "umi-pw-toggle";
    button.setAttribute("aria-controls", input.id);
    button.setAttribute("aria-pressed", "false");
    button.textContent = "Show password";

    button.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.setAttribute("aria-pressed", showing ? "false" : "true");
      button.textContent = showing ? "Show password" : "Hide password";
    });

    // Hidden again before the form is sent, so the browser files it as a password.
    if (input.form) {
      input.form.addEventListener("submit", function () {
        input.type = "password";
      });
    }

    input.insertAdjacentElement("afterend", button);
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
