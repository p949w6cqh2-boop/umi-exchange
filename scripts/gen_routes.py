#!/usr/bin/env python
"""Generate the routes reference (Method · Path · View · Auth · Name) from the LIVE
URLconf — so docs/routes.md can't drift from code. There is no OpenAPI/Swagger
(no REST API; DRF was removed in PR #16), so this is the routes contract.

    .venv/bin/python scripts/gen_routes.py > docs/routes-generated.md   # regenerate
    .venv/bin/python scripts/gen_routes.py | diff - <(sed -n '/^| Method/,$p' docs/routes.md)

Method/Path/View/Name come from URL introspection. **Auth cannot** — it lives in
each view's mixin/decorator, so we read LoginRequiredMixin off the view class.
Finer role-gating (coordinator/admin/owner) lives in dispatch()/get_object()
logic, not a mixin, so it is NOT in the Auth column — see the view.
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.urls import get_resolver  # noqa: E402

# HTML app, no REST (DRF removed) → only GET/POST are real. Generic CBVs also
# inherit framework put/patch/delete handlers (e.g. ProcessFormView.put), but the
# app never uses them, so they'd be noise in the contract.
HANDLERS = ("get", "post")
SKIP_PREFIXES = ("admin/",)  # Django admin is framework, not app routes


def view_meta(callback):
    vc = getattr(callback, "view_class", None)
    if vc is None:  # function-based view
        # @login_required wraps the function; we can't reliably introspect it.
        return (getattr(callback, "__name__", "fbv"), "GET", "see view")
    methods = ",".join(m.upper() for m in HANDLERS if hasattr(vc, m)) or "GET"
    mro = {c.__name__ for c in vc.__mro__}
    auth = "login" if "LoginRequiredMixin" in mro else "public"
    return (vc.__name__, methods, auth)


def walk(patterns, prefix=""):
    rows = []
    for p in patterns:
        pat = str(p.pattern)
        full = prefix + pat
        if hasattr(p, "url_patterns"):  # include()
            rows += walk(p.url_patterns, full)
            continue
        if any(full.startswith(s) for s in SKIP_PREFIXES):
            continue
        view, methods, auth = view_meta(p.callback)
        rows.append((methods, "/" + full.lstrip("/"), view, auth, p.name or ""))
    return rows


HEADER = """# Routes reference (generated)

> **Generated from the live URLconf** by `scripts/gen_routes.py` — do not hand-edit.
> Regenerate: `.venv/bin/python scripts/gen_routes.py > docs/routes.md`.
>
> There is **no OpenAPI/Swagger**: UMI Exchange is server-rendered HTML + HTMX with
> **no REST API** (DRF was removed in PR #16), so this table is the route contract.
>
> **Method / Path / View / Name** come from URL introspection. **Auth** is read off
> each view's `LoginRequiredMixin` (`login` vs `public`). Finer role-gating
> (coordinator / admin / owner / case participant) lives in `dispatch()` /
> `get_object()` / `apps/casework/access.py::case_access()` logic — **not** a mixin —
> so it is NOT in the Auth column; read the view. Namespaced includes (`cases/`,
> `tags/`) resolve **before** the `c/` communities catch-all.
"""


def main():
    rows = walk(get_resolver().url_patterns)
    print(HEADER)
    print("| Method | Path | View | Auth | Name |")
    print("|---|---|---|---|---|")
    for methods, path, view, auth, name in rows:
        print(f"| {methods} | `{path}` | {view} | {auth} | `{name}` |")
    print(f"\n_{len(rows)} routes, generated from the live URLconf by `scripts/gen_routes.py`._")


if __name__ == "__main__":
    main()
