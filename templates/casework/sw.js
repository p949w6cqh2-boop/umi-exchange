{% load static %}// UMI casework offline visit-capture service worker (design §3.6, item 4).
// Served from /c/<slug>/cases/visit/sw.js so its scope is limited to the visit
// routes — it can never cache the rest of the app. It precaches the visit shell
// so a coordinator can cold-load the capture form with no connectivity; the
// case list (short codes + initials only) and queued drafts live in IndexedDB,
// managed by visit_offline.js, not here.
"use strict";

var CACHE = "umi-casework-visit-v1";
var VISIT_URL = "{% url 'casework:visit' slug=community.slug %}";
var SHELL = [VISIT_URL, "{% static 'casework/visit_offline.js' %}"];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE)
      .then(function (cache) { return cache.addAll(SHELL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(
          keys.filter(function (k) { return k !== CACHE; })
              .map(function (k) { return caches.delete(k); })
        );
      })
      .then(function () { return self.clients.claim(); })
  );
});

// Navigation requests → network-first, falling back to the cached visit shell
// when offline. Other same-origin GETs → cache-first with a background fill.
// Non-GET (the POST sync) is never intercepted — visit_offline.js syncs the
// IndexedDB queue online-only, honoring the 4-hour re-auth rule.
self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(function () { return caches.match(VISIT_URL); })
    );
    return;
  }
  event.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (resp) {
        var copy = resp.clone();
        caches.open(CACHE).then(function (cache) { cache.put(req, copy); });
        return resp;
      });
    })
  );
});
