// reCAPTCHA for sending a phone code (apps/accounts/phone.py, Firebase provider). Google requires
// a token with every send. The widget is invisible: pressing the button asks Google for a token,
// and only people Google is unsure about see a puzzle. This file must load BEFORE Google's script
// (both are `defer`, so they run in order), because Google calls umiRecaptchaReady when it is up.
window.umiRecaptchaReady = function () {
  "use strict";
  var forms = document.querySelectorAll("form[data-recaptcha-form]");
  Array.prototype.forEach.call(forms, function (form) {
    var slot = form.querySelector("[data-sitekey]");
    var input = form.querySelector('input[name="recaptcha_token"]');
    if (!slot || !input) return;
    var id = window.grecaptcha.render(slot, {
      sitekey: slot.getAttribute("data-sitekey"),
      size: "invisible",
      badge: "inline", // inside the form, not floating over the phone's bottom menu
      callback: function (token) {
        input.value = token;
        form.submit(); // does not fire "submit" again, so no loop
      },
    });
    form.addEventListener("submit", function (event) {
      if (input.value) return;
      event.preventDefault();
      window.grecaptcha.execute(id);
    });
  });
};
