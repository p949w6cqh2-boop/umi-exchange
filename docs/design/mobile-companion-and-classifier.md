# Design — RN volunteer companion + self-hostable need classifier

> **STATUS: DESIGNED (design-only, no code). STOP for approval.** Read-only analysis. Builds on the
> Lakes Operating Manual (offline visit capture §8.x; consent/audit §8.3, §5.x) and
> [`../network-security-addendum.md`](../network-security-addendum.md) (self-host / on-prem posture).
> Verified against code: the existing offline-sync contract (`SyncView`, `static/casework/visit_offline.js`,
> `apps/casework/tests/test_sync_offline.py`, `SensitiveSessionMiddleware`) and `communities_category`.
>
> **Two hard rules this design reconciles up front:**
> 1. **No DRF / no REST framework / no OpenAPI.** The existing casework sync endpoint is already a
>    *hand-rolled* `JsonResponse` view (no DRF). All mobile endpoints below follow that exact pattern.
> 2. **Reuse the existing sync contract** — the `client_uuid` idempotency + conflict model. The RN app is
>    a **native port** of `visit_offline.js`, **not a second sync protocol.**

---

## Part 1 — React Native volunteer companion

### 1.1 What already exists (the contract to port)

`POST /c/<slug>/cases/sync/` (hand-rolled JSON) takes `{"drafts": [...]}` and returns
`{"results": [{"status": "created|duplicate", "note_id", "dup_warning"?}]}`:
- **Idempotency:** `client_uuid` (a `CaseNote` unique column). Replay → `duplicate` + the same `note_id`.
- **Soft conflict:** same case + same hour → `dup_warning` (flag, not rejection). State-machine clashes → `409`.
- **Sensitive gate:** stale 4-hr session → `403 {"reauth": true}` (so the client keeps its queue).

The RN app mirrors this exactly; the only new surface is **token auth** (web uses session cookies) and
**push**.

### 1.2 Screens (text mockups)

| # | Screen | Purpose | Notes |
|---|---|---|---|
| S1 | **Sign in** | username + password → device token | rate-limited; biometric unlock on subsequent opens |
| S2 | **Re-auth** | password / biometric to refresh the 4-hr sensitive window | mirrors web reauth; required before decrypt screens |
| S3 | **My cases** | assigned/accessible cases (titles only) | server-filtered by `case_access()`; pull-to-refresh |
| S4 | **Case detail** | notes timeline, follow-ups (decrypted in-memory only) | sensitive → requires fresh S2 |
| S5 | **Record visit** | the 3-minute form (kind, actions, duration, body) — works **offline** | writes a local encrypted `VisitDraft` |
| S6 | **Sync queue** | pending/synced/duplicate/conflict drafts + retry | the sync state machine (§1.5) made visible |
| S7 | **Matches** | "you have an urgent match — open to view" | detail behind auth (S4-style); never in the push body |
| S8 | **Settings** | remote-logout this device, wipe local data, privacy notice | logout → revoke token + purge encrypted store |

```
S5 Record visit (offline-capable)
┌───────────────────────────────┐
│ Case: ░░░░ (short code only)   │
│ Kind:  [Home visit ▾]          │
│ Actions: [Food][Utility][…]    │
│ Duration: [ 25 ] min           │
│ Notes: ░░░░░░░░░░░░ (encrypted) │
│ [ Save offline ]  ⛁ 3 queued   │  ⛁ = encrypted local queue
└───────────────────────────────┘
```

```
S7 push (data-only — NO beneficiary text)
{ "type": "match_available", "community": "<slug>", "count": 1 }
→ tap → open app → authed fetch of detail (never in the payload)
```

### 1.3 Data model

**On device (encrypted at rest — §1.6):**

| Store | Fields | Notes |
|---|---|---|
| `VisitDraft` (local) | `client_uuid` (UUID, generated on device), `case_id`, `kind`, `occurred_at`, `duration_minutes`, `location_kind`, `actions[]`, `aid_value_cents`, `body`, `sync_state` | mirrors the sync payload 1:1; `client_uuid` is the dedup key |
| `Session` (local) | token (in Keychain/Keystore, **not** the DB), `member_id`, `sensitive_at`, scopes | token never in plaintext storage or logs |

**Server (new — DESIGNED):** `DeviceToken` (see §1.4). **No change** to `CaseNote` — the existing
`client_uuid` column already carries offline idempotency.

### 1.4 Endpoints (all hand-rolled `JsonResponse`, no DRF, no OpenAPI)

| Method | Path | Auth | Body → Response | Notes |
|---|---|---|---|---|
| POST | `/m/auth/token` | password (rate-limited) | `{username,password,device_id}` → `{token, scopes, expires_at}` | issues a scoped device token |
| POST | `/m/auth/reauth` | token | `{password}` → `{sensitive_at}` | refreshes the 4-hr sensitive window (mobile parallel of web reauth) |
| POST | `/m/auth/logout` | token | `{}` → `{revoked:true}` | revokes this token (remote logout) |
| POST | `/c/<slug>/cases/sync/` | token + fresh sensitive | **reuse the existing contract** (`{drafts:[…]}`) | same view, token-auth path added; same `client_uuid`/`409`/`dup_warning` |
| GET | `/m/cases/` / `/m/cases/<id>/` | token + fresh sensitive | → case list / detail JSON | server-filtered by `case_access()`; decrypt in-memory only |
| GET | `/m/matches/poll` | token | → `{count, match_ids}` (no PII) | drives S7 badge; detail via authed fetch |
| POST | `/m/push/register` | token | `{platform, push_token}` → `{ok}` | stores APNs/FCM token for this device |

**Token scheme (minimal, scoped, revocable — no DRF token framework):** opaque CSPRNG token; stored
server-side as a **salted SHA-256 hash** (same pattern as audit IPs — never the raw token), `member` FK,
`scopes` (e.g. `casework.sync`, `match.read`), `expires_at`, `revoked_at`, `sensitive_at`, `device_id`,
`last_seen`. A small `@require_token(scope=…)` decorator validates `Authorization: Bearer <token>` for the
`/m/` views (parallel to `LoginRequiredMixin`). **Sensitive endpoints** additionally require
`now - sensitive_at < 4h`, else `401 {"reauth": true}` — the mobile analogue of `SensitiveSessionMiddleware`.

### 1.5 Sync / conflict state machine (per draft)

```
            save offline
   ( • ) ──────────────► QUEUED
                           │ POST /cases/sync/  (online + fresh sensitive)
                           ▼
                        SYNCING ──403 {reauth}──► NEEDS_REAUTH ──(S2)──► QUEUED
                           │
        ┌──────────────────┼───────────────────┬───────────────┐
     "created"         "duplicate"       "dup_warning"        409
        ▼                  ▼                   ▼                ▼
      SYNCED          SYNCED(dedup)     SYNCED + WARN      CONFLICT (review)
   (server note_id)  (same note_id)   (coordinator sees)  (manual resolve)
```

Idempotent by `client_uuid` (replay-safe); the client keeps the queue across `403 reauth`; same-hour
`dup_warning` surfaces in S6 for human judgment (never auto-discarded).

### 1.6 Device risk (beneficiary PII on a personal phone)

- **Encrypted at rest:** local drafts/notes in **SQLCipher** (or an encrypted store); the DB key lives in
  **iOS Keychain / Android Encrypted Shared Preferences** (per RN security guidance), never in the JS
  bundle, AsyncStorage, or the DB itself.
- **Remote logout / wipe:** `/m/auth/logout` revokes the token server-side; a `wipe` push (data-only) or
  the next `401` triggers the app to purge the encrypted store. Lost phone → revoke from S8 on another device.
- **No PII in local logs / crash reports** (Sentry `send_default_pii=False` already; mirror on mobile).
- **Push payloads carry NO beneficiary text** — only `{type, community, count}`; detail is always an
  authed fetch behind S2/S4. (APNs/FCM are third parties.)

---

## Part 2 — Self-hostable need-category classifier

### 2.1 Stance

- **Community-aware.** `communities_category` is **per-community** (FK to `Community`). The classifier
  suggests from **that community's** active category set — a new community brings new categories, so there
  is **no global fixed taxonomy**. Design must be **zero-shot** over an arbitrary category set, with an
  optional per-community trained upgrade.
- **Suggestion only.** Output is ranked suggestions; a coordinator/volunteer **confirms or overrides**.
  **Never auto-assign.**
- **Privacy is a hard requirement.** Need text can contain beneficiary PII → inference is **on-device /
  self-hosted only, never a third-party API**. Training data (labeled beneficiary text) is sensitive →
  **de-identified, kept on-instance, consent-aware, never exported.**

### 2.2 Model choice (criteria: modest parish hardware, no GPU, fully offline)

| Option | How | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. TF-IDF + linear (scikit-learn / liblinear)** | per-community classifier over confirmed labels | tiny (<5 MB), instant CPU inference, interpretable | needs labeled data per community; cold-start weak | **per-community upgrade** once confirmations accumulate |
| **B. Small sentence-embedding, zero-shot** (e.g. `all-MiniLM-L6-v2`, ~80 MB, **ONNX runtime, CPU**) | embed need text + each category's name/description; rank by cosine similarity | **works for any community immediately, no training**; CPU-only, offline | ~80 MB model; embedding cost ~ms on CPU | **default / recommended** |
| C. Local LLM (e.g. small instruct model) | prompt with categories | flexible | heavy, often needs GPU, overkill | rejected (hardware) |

**Recommendation: B as the default** (zero-shot, no labeled data, runs on a parish CPU box, fully
offline), with **A as an opt-in per-community refinement** trained from accumulated coordinator
confirmations (active learning). Both run **on the instance**; neither calls out.

### 2.3 Integration API (hand-rolled JSON, same pattern)

| Method | Path | Body → Response |
|---|---|---|
| POST | `/c/<slug>/classify` | `{title, description}` → `{suggestions:[{category_id, name, score}], model_version}` |

Used by the need/offer create form (web + S5 mobile): show top-3 suggestions, pre-select none, human
confirms. Inference runs **in-process or a local sidecar** (ONNX runtime on the same host) — no network
egress. Returns fast or the form proceeds without a suggestion (never blocks).

### 2.4 Training data (de-identified, on-instance, consent-aware)

- **Source:** coordinator confirmations — `(need_text, confirmed_category_id, community_id)`.
- **Format (JSONL, on-instance only):** `{"text": "<de-identified>", "category_id", "community_id", "confirmed_by", "ts"}`.
- **De-identify before storing as training data:** strip names/contacts/addresses (reuse the existing
  sanitization patterns); store only the de-identified text. **Consent-aware** (exclude records whose
  consent scope forbids secondary use). **Never exported** off the instance; retrainable locally.

---

## Open questions for approval
1. **`DeviceToken` model** — net-new model + migration (the one schema change). OK to add, or keep tokens
   stateless-signed (HMAC) to avoid a table? (Stateful is easier to **revoke** → recommended.)
2. **`/m/` URL prefix + a `@require_token` decorator** vs. extending the existing views with a token path.
3. **Classifier packaging** — bundle the ONNX model in the image vs. a `manage.py fetch_model` step (offline installs).
4. **Push provider** — APNs + FCM directly, or a self-hostable relay (UnifiedPush) to avoid Google/Apple entirely?

_DESIGN ONLY — no code, no schema applied, no cloud-AI dependency. Hand back for approval; on approval this
becomes staged build briefs (token auth → mobile sync port → classifier sidecar), each behind the verify gate._
