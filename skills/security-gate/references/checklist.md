# Security checklist

Mark every item ✅ (done, with evidence), ⚠️ (problem or unverified) or N/A. Evidence is a `file:line`, a setting or a test.

## The five essentials (every review, and always before launch)

| # | Risk | Must be true | Automated help |
|---|---|---|---|
| 1 | **SQL and filter injection** | Every input is validated on the server with a schema (zod or similar). Client checks do not count. Queries use parameters or a query builder, never strings built from input. In plpgsql, dynamic SQL uses `format()` with `%I` and `%L`, or `USING`. | `sql-interpolation`, `sql-concat`, `postgrest-filter`, `sql-dynamic`, `input-validation` |
| 2 | **Brute force** | Login, one-time codes and password reset limit attempts per account and per IP (for example, a short lockout after 5 failures), and add a CAPTCHA after repeated failures. Error messages do not reveal whether an account exists. | `bruteforce` |
| 3 | **Password hashing** | Passwords are handled by the auth provider, or hashed with argon2id, bcrypt or scrypt. Never md5 or sha*, never stored or logged in plain text. Reset tokens are single-use and expire. | `weak-hash`, `password-log` |
| 4 | **File uploads** | Size limit and type allowlist are enforced on the server or in bucket settings. Types are checked by content, not just extension. Stored names are random. Buckets are private with signed URLs unless the files are meant to be public. User-uploaded HTML or SVG is never served inline. Image metadata (EXIF location) is stripped when privacy matters. | `upload-unchecked`, `upload-partial`, `upload-client`, `public-bucket` |
| 5 | **Vulnerable dependencies** | `security.py audit` shows nothing at or above the configured level, or each remaining advisory has a recorded reason. New packages are maintained and widely used. CI runs the audit on every PR, and Dependabot or Renovate is on. | `audit` |

## Authentication (`auth`)
- Session cookies are `HttpOnly`, `Secure` and `SameSite`. Logout invalidates the session on the server.
- OAuth and magic-link redirect targets come from an allowlist.
- Email change, password change and account deletion require the current session plus re-authentication or confirmation.
- Admin accounts use strong authentication (MFA where available).

## Authorization (`authz`, `migrations`)
- Every server entry point (server actions, route handlers, RPC and database functions, storage policies) checks the user and role itself. Hiding a button is not authorization.
- Row-level security is enabled on every table the client can reach, with a policy for each operation the app needs and nothing more.
- `security definer` functions set `search_path`, check the caller again, and are the only way to the data they protect.
- No broad `grant` to anonymous roles. Every grant matches a policy.
- Tests or real queries prove that each role sees and changes only what it should, including direct API calls that skip the UI.
- Time of check versus time of use: the permission check and the write happen together (same statement, transaction or policy).

## Money (`money`)
- Amounts, prices and discounts are computed on the server from trusted data, never taken from the client.
- Payment, refund and webhook handlers are idempotent (unique keys, status checks).
- Webhook signatures are verified, with a timestamp window against replays.
- Reconciliation is possible: every money event leaves a record.

## Secrets (`secrets`)
- No secret is in the repository, logs, client bundles or public env vars (`NEXT_PUBLIC_`, `VITE_` and similar).
- Admin keys (for example Supabase `service_role`) are used only in server code guarded with `server-only`.
- Secrets differ per environment, and preview deployments do not get production secrets unless that is intended.
- Leaked secrets are rotated, not just deleted.

## Personal data (`personal-data`)
- Collect only what the feature needs, and say why at the point of collection.
- Only the people who need it can read it (policies and roles). It is masked in logs, URLs and analytics.
- Retention and deletion are defined. Exports and backups are protected the same way.

## Webhooks (`webhook`)
- Signature verification is done on the raw body, comparing in constant time.
- Unknown event types are ignored safely. Handlers are idempotent.

## Web (always for UI and API changes)
- XSS: no unsanitized HTML injection (`dangerouslySetInnerHTML`, `innerHTML`, `v-html`).
- Open redirects: redirect targets are same-site paths or allowlisted.
- CORS is limited to known origins for authenticated APIs.
- CSRF: requests that change state are protected (framework defaults, `SameSite` cookies, origin checks).
- SSRF: the server never fetches arbitrary user-supplied URLs without an allowlist.
- Security headers: CSP where practical, `X-Content-Type-Options`, `Referrer-Policy`, frame protection.

## Stack notes

**Supabase**
- Supabase Auth hashes passwords for you. Check the auth rate limits and enable CAPTCHA (hCaptcha or Turnstile) in the project's auth settings or in `supabase/config.toml` (`[auth.rate_limit]`).
- Storage buckets: set `file_size_limit` and `allowed_mime_types`, keep buckets private, and write policies on `storage.objects`.
- `.or()` and `.filter()` take raw filter strings. Never interpolate user input into them.
- The anon key is public by design. Safety comes from RLS, so every exposed table needs it.

**Next.js**
- Server actions are public HTTP endpoints. Validate input and check auth inside each one.
- Use `import "server-only"` for admin clients. Middleware alone is not authorization.

**Vercel**
- Protect preview deployments when they use real data. Scope env vars per environment.

**Firebase**
- Security rules for Firestore and Storage are the authorization layer. Test them with the emulator.
- Enable App Check for client-facing APIs.
