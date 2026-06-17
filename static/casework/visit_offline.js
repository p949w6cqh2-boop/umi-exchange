/* Offline visit capture (design §3.6, item 4).
 * - Registers the scope-limited service worker.
 * - When offline, intercepts the visit form submit, queues the draft in
 *   IndexedDB (client_uuid = idempotency key), and shows the queue banner.
 * - On reconnect (or page load), POSTs the queue to /cases/sync/; replies of
 *   "created"/"duplicate" clear items; a 403 {"reauth": true} keeps the
 *   queue and surfaces the re-auth link (4-hour rule).
 * The only PII cached is the note body the user typed into their own queued
 * drafts; it is encrypted at rest in IndexedDB with a non-extractable
 * AES-GCM key and decrypted only in-memory, just before sync. The cached
 * case list is short codes + initials only. */
(function () {
  "use strict";
  var form = document.getElementById("visit-form");
  if (!form) return;

  var syncUrl = form.dataset.syncUrl;
  var manifestUrl = form.dataset.manifestUrl;
  var swUrl = form.dataset.swUrl;
  var banner = document.getElementById("offline-banner");
  var bannerText = document.getElementById("offline-banner-text");
  var reauthLink = document.getElementById("offline-reauth-link");

  // ---- service worker (scope = .../cases/visit/) ----
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register(swUrl).catch(function () {});
  }
  // warm the offline manifest cache
  fetch(manifestUrl, { credentials: "same-origin" }).catch(function () {});

  // ---- tiny IndexedDB queue ----
  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open("casework-drafts", 2);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains("drafts")) {
          db.createObjectStore("drafts", { keyPath: "client_uuid" });
        }
        if (!db.objectStoreNames.contains("keys")) {
          db.createObjectStore("keys", { keyPath: "id" });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }
  function withStore(mode, fn) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction("drafts", mode);
        var out = fn(tx.objectStore("drafts"));
        tx.oncomplete = function () { resolve(out && out.result); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }
  function allDrafts() {
    return openDb().then(function (db) {
      return new Promise(function (resolve) {
        var items = [];
        var cur = db.transaction("drafts").objectStore("drafts").openCursor();
        cur.onsuccess = function (e) {
          var c = e.target.result;
          if (c) { items.push(c.value); c.continue(); } else { resolve(items); }
        };
      });
    });
  }

  // ---- at-rest encryption for the note body (WebCrypto, non-extractable key) ----
  var subtle = window.crypto && window.crypto.subtle ? window.crypto.subtle : null;

  function getKey() {
    // Resolves to a non-extractable AES-GCM CryptoKey, creating + persisting one
    // on first use. Resolves null when WebCrypto is unavailable (e.g. an
    // insecure context) so capture degrades to plaintext rather than failing.
    if (!subtle) return Promise.resolve(null);
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var get = db.transaction("keys").objectStore("keys").get("draft-key");
        get.onsuccess = function () {
          if (get.result && get.result.key) { resolve(get.result.key); return; }
          subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"])
            .then(function (key) {
              return openDb().then(function (db2) {
                return new Promise(function (res, rej) {
                  var tx = db2.transaction("keys", "readwrite");
                  tx.objectStore("keys").put({ id: "draft-key", key: key });
                  tx.oncomplete = function () { res(key); };
                  tx.onerror = function () { rej(tx.error); };
                });
              });
            })
            .then(resolve, reject);
        };
        get.onerror = function () { reject(get.error); };
      });
    });
  }

  function encryptBody(text) {
    // -> {body_ct, body_iv} when crypto is available, else {body: text}.
    return getKey().then(function (key) {
      if (!key) return { body: text };
      var iv = window.crypto.getRandomValues(new Uint8Array(12));
      return subtle.encrypt({ name: "AES-GCM", iv: iv }, key, new TextEncoder().encode(text))
        .then(function (ct) { return { body_ct: ct, body_iv: iv }; });
    }).catch(function () { return { body: text }; });
  }

  function decryptBody(draft) {
    // -> plaintext string. Handles encrypted drafts and legacy plaintext ones.
    if (draft.body_ct == null) return Promise.resolve(draft.body || "");
    if (!subtle) return Promise.resolve("");  // can't recover without WebCrypto
    return getKey().then(function (key) {
      if (!key) return "";
      return subtle.decrypt({ name: "AES-GCM", iv: new Uint8Array(draft.body_iv) }, key, draft.body_ct)
        .then(function (pt) { return new TextDecoder().decode(pt); });
    });
  }

  function getCookie(name) {
    var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }
  function setUuid() {
    var field = form.querySelector('input[name="client_uuid"]');
    if (field) field.value = (crypto.randomUUID ? crypto.randomUUID() : "");
  }
  function showBanner(text, needReauth) {
    banner.hidden = false;
    bannerText.textContent = text;
    reauthLink.hidden = !needReauth;
  }
  function refreshBanner() {
    allDrafts().then(function (items) {
      if (items.length) {
        showBanner(items.length + " visit(s) queued on this device — " +
          (navigator.onLine ? "syncing…" : "will sync when you're back online."), false);
      } else if (navigator.onLine) {
        banner.hidden = true;
      }
    });
  }

  // ---- offline submit interception (online submits post normally) ----
  form.addEventListener("submit", function (e) {
    if (navigator.onLine) return;  // plain POST fallback path
    e.preventDefault();
    var checked = [];
    form.querySelectorAll('input[name="actions"]:checked').forEach(function (el) {
      checked.push(el.value);
    });
    var aid = parseFloat(form.querySelector('[name="aid_amount"]').value || "");
    var body = form.querySelector('[name="body"]').value;
    var draft = {
      client_uuid: form.querySelector('[name="client_uuid"]').value,
      case_id: form.querySelector('[name="case"]').value,
      kind: form.querySelector('[name="kind"]').value,
      occurred_at: form.querySelector('[name="occurred_at"]').value,
      duration_minutes: form.querySelector('[name="duration_minutes"]').value || null,
      location_kind: form.querySelector('[name="location_kind"]').value,
      actions: checked,
      aid_value_cents: isNaN(aid) ? null : Math.round(aid * 100),
      finalize: !!(e.submitter && e.submitter.name === "finalize"),
    };
    if (!draft.case_id || !body) {
      showBanner("Pick a case and write a note before saving.", false);
      return;
    }
    // Encrypt the note body before it touches disk — never stored in the clear.
    encryptBody(body).then(function (enc) {
      if (enc.body_ct) { draft.body_ct = enc.body_ct; draft.body_iv = enc.body_iv; }
      else { draft.body = enc.body; }
      return withStore("readwrite", function (s) { return s.put(draft); });
    }).then(function () {
      form.reset(); setUuid(); refreshBanner();
    });
  });

  // ---- flush queue ----
  var flushing = false;
  function flush() {
    if (flushing || !navigator.onLine) return;
    allDrafts().then(function (items) {
      if (!items.length) { refreshBanner(); return; }
      flushing = true;
      // Decrypt each body in-memory and build a plaintext copy for the wire;
      // the stored objects keep their ciphertext.
      Promise.all(items.map(function (it) {
        return decryptBody(it).then(function (body) {
          var out = {};
          for (var k in it) { if (k !== "body_ct" && k !== "body_iv") out[k] = it[k]; }
          out.body = body;
          return out;
        });
      })).then(function (wire) {
        return fetch(syncUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json",
                     "X-CSRFToken": getCookie("csrftoken") },
          body: JSON.stringify({ drafts: wire }),
        });
      }).then(function (resp) {
        if (resp.status === 403) {
          return resp.json().then(function (j) {
            if (j && j.reauth) {
              showBanner("Queued visits are waiting — confirm your password to sync.", true);
            }
            throw new Error("reauth");
          });
        }
        return resp.json();
      }).then(function (data) {
        var dup = false;
        var ops = (data.results || []).map(function (r) {
          if (r.status === "created" || r.status === "duplicate") {
            if (r.dup_warning) dup = true;
            return withStore("readwrite", function (s) { return s.delete(r.client_uuid); });
          }
          return Promise.resolve();
        });
        return Promise.all(ops).then(function () {
          refreshBanner();
          if (dup) showBanner("Synced — one visit looks like a possible duplicate; " +
            "a coordinator will see a review prompt on the case.", false);
        });
      }).catch(function () { /* keep the queue */ })
        .finally(function () { flushing = false; });
    });
  }

  window.addEventListener("online", function () { refreshBanner(); flush(); });
  window.addEventListener("offline", refreshBanner);
  setUuid();
  refreshBanner();
  flush();
})();
