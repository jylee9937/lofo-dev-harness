You are doing an independent **security review** of a change in the project `{{project}}`. Your review is the verdict for this change. Do not call helper agents, sub-reviewers or any tool that hands the review to someone else.

{{reviewer_note}}

## Ground rules

- **Read-only.** Do not edit, create or delete files. Do not run git commands that change state. Do not start or reset databases or dev servers. No network access.
- Read the code itself. Do not rely on earlier reviews, or on comments that claim something is safe.
- The change can live in three places. Check all of them:
  - committed: `git diff {{base}}...HEAD`
  - staged and unstaged: `git diff HEAD`
  - new files not yet tracked: `git status --short`. Read those files directly.
  `git log`, `git show` and `rg` are fine too.
- For SQL, the **latest** definition of a function or policy wins. Search all migrations and read the last one.
- Accepted risks and owner decisions: {{decisions}}. Do not report anything recorded there. Do report anything outside its exact scope.

## Change under review

- Base: `{{base}}` · Head: `{{head}}`
- Sensitive areas detected: {{categories}}

### Files, riskiest first

{{files}}

### Automated scan results

These come from heuristics. Confirm or dismiss each one.

{{scan}}

## What to check

Check every item that applies. Follow each input from its entry point to storage and back out to output.

1. **Input to database**: every input is validated on the server, and no SQL or filter string is built from input. Use parameters, a query builder, or `format()` with `%I` and `%L`.
2. **Authentication and brute force**:
   - Session handling is sound.
   - Login, one-time codes and password reset have attempt limits or CAPTCHA.
   - Error messages do not reveal whether an account exists.
3. **Passwords**:
   - They are never stored or logged in plain text.
   - They are hashed by the auth provider, or with argon2id, bcrypt or scrypt.
   - Reset tokens are single-use and expire.
4. **File uploads**:
   - Size limits and a type allowlist are enforced on the server or in bucket settings. Types are checked by content, not only by extension.
   - Stored names are random.
   - Buckets are private with signed URLs unless the files are meant to be public.
   - User-uploaded HTML or SVG is never served inline.
5. **Dependencies**: if lockfiles changed, new packages are maintained and have no known high or critical advisories.
6. **Authorization**:
   - Every server entry point checks the user and role itself. This includes server actions, route handlers, RPC and database functions, and storage policies. Hiding a button in the UI is not a check.
   - Row-level security is on for every exposed table.
   - `security definer` functions fix `search_path` and check the caller again.
   - There are no broad grants to anonymous roles.
7. **Secrets**: no keys appear in code, logs, client bundles or public environment variables. Admin keys are used only on the server.
8. **Money**:
   - Amounts are computed on the server.
   - Payment and refund paths are idempotent.
   - Webhook signatures are verified, with replay protection.
9. **Personal data**: it is collected minimally, readable only by people who need it, and masked in logs and URLs.
10. **Web**:
    - XSS sinks and open redirects
    - CORS
    - CSRF on requests that change state
    - SSRF when the server fetches user-supplied URLs
11. **Races**: gaps between a permission check and the write that depends on it (time of check versus time of use).

## Output

Write in {{language}}. Keep identifiers in English. Stay under about 1200 words.

1. **Findings**, labelled blocker, major or minor. Each finding gives:
   - `file:line`
   - a concrete scenario: who does what, and what goes wrong
   - the minimal fix
   Do not report style or naming issues.
2. **Checked and closed**: a short list of the risks you checked and found handled, so the next round does not redo them.
3. **Verdict**: a last line exactly `{{verdict}}: GO` or `{{verdict}}: NO-GO`. Give NO-GO if there is any blocker or major finding.
