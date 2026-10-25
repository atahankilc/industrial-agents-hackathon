# Landing account button: sign in, preferences, set a password, sign out

- **Author:** Claude session (Atahan) · **Date:** 2026-10-25
- **Related:** access mode (`frontend/app/src/access/`)

## Summary
On the landing (map / list, no building open) access mode now shows an account button top right: "Sign in" when
signed out; when signed in, the email (+ "admin" tag) opening a menu with Preferences, Set a password (only when
needed) and Sign out. The building screen already has these items in its "…" menu.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `Root` passes `landing={!shown}` to `AccessLayer` | `frontend/app/src/Root.tsx` | read the diff |
| C2 | `AccessLayer` takes an optional `landing` prop (default false) and renders `<Account />` only when it is true; still renders nothing when access mode is off | `frontend/app/src/access/AccessLayer.tsx:AccessLayer` | read the diff |
| C3 | `Account` shows "Sign in" (opens the signin panel) when no email; otherwise an email button toggling a menu with Preferences, Set a password (only if `needsPassword`), Sign out, and an admin-only hint | `frontend/app/src/access/AccessLayer.tsx:Account` | read the diff |
| C4 | New CSS for `.account-corner`, `.account-button`, `.account-email`, `.account-role`, `.account-menu`, `.account-hint` using existing `--hud-*` variables | `frontend/app/src/access/access.css` | read the diff |
| C5 | Frontend typechecks | `frontend/app` | `cd frontend/app && npx tsc -b --noEmit` → exit 0 |

## Checks I ran
- `cd frontend/app && npx tsc -b --noEmit` → `tsc exit 0`

## Knowledge base updates
- [ ] `memory-bank/project-state.md` updated — not needed: small UI addition, user asked for a direct commit
- [ ] `memory-bank/log.md` entry added — not needed (same reason)
- [ ] decisions / open questions touched: none
- [ ] docs touched: none

## Known gaps / not done
- Not tried in the browser (no screenshot / manual check of the menu or phone layout).
- Menu does not close on outside click or Escape; only on toggling the button or picking an item.
