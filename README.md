# OwnIt

**AI understands your code. But do you?**

OwnIt (`defend-your-pr`) is a pull-request understanding checkpoint. Opening a PR or pushing another commit creates a pending GitHub check. The PR author must explain the actual changes, their consequences, and edge cases before the check can pass and the PR becomes eligible to merge.

The main workflow is **PR → blocked merge check → diff-specific quiz → teach/retest → passed check for that commit**. Repository analysis supplies context to the quiz. See [GitHub checkpoint setup](docs/GITHUB_SETUP.md) to connect a repository and require the check; the local website alone cannot enforce a merge restriction.

## Requirements and installation

- Python 3.11+ (tested: 3.13.9), Node.js 22.14+ and npm (tested: Node 22.14.0).
- SQLite is included in Python. No database server is required.
- Live reviews need internet and a Dartmouth AI API key. Demo Mode needs neither.

PowerShell, from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env
cd frontend
npm ci
cd ..
```

If Python is not on PATH on this machine, create the environment using:

```powershell
& 'C:\Users\ericr\anaconda3\python.exe' -m venv .venv
```

This checkout also has an ignored portable Node runtime downloaded from nodejs.org during development. If Node is not on PATH, run this from the root before using npm:

```powershell
$env:Path = "$PWD\tools\node-v22.14.0-win-x64;" + $env:Path
```

On macOS/Linux use `python3 -m venv .venv`, `.venv/bin/python -m pip install -e '.[dev]'`, and `cp .env.example .env`. The npm commands are identical.

## Launch

Terminal 1, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn ownit.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2, from the repository root:

```powershell
cd frontend
npm run dev
```

Open **http://localhost:3000**. Use `localhost` in the browser to match the default CORS origin. API docs: http://localhost:8000/docs. Health: http://localhost:8000/health. Stop servers with Ctrl+C.

For a production frontend, run `npm run build` then `npm run start` from `frontend/`. On macOS/Linux, the backend command uses `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

## Environment variables

The backend reads the root `.env` automatically. Never place server credentials in frontend files or `NEXT_PUBLIC_*` variables.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DARTMOUTH_API_KEY` | `PASTE_YOUR_DARTMOUTH_API_KEY_HERE` | Replace this placeholder with your Dartmouth AI key for live analysis, grading and tutoring |
| `DARTMOUTH_API_BASE_URL` | `https://chat.dartmouth.edu/api` | Dartmouth Chat API base URL |
| `DARTMOUTH_MODEL` | `anthropic.claude-sonnet-5-5` | Claude Sonnet 5.5; confirm this model ID is available to your Dartmouth account |
| `GITHUB_TOKEN` | empty | Server token with Contents read and Commit statuses write for connected public repositories |
| `OWNIT_REPOSITORIES` | empty | Comma-separated `owner/repo` allowlist for live checkpoints |
| `GITHUB_WEBHOOK_SECRET` | empty | Shared secret for signed PR webhooks |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | empty | GitHub OAuth App credentials for PR-author identity verification |
| `OWNIT_APP_URL` | `http://localhost:3000` | Frontend URL used in the GitHub check's Details link |
| `OWNIT_API_URL` | `http://localhost:8000` | Backend URL used for the OAuth callback |
| `OWNIT_DB` | `data/ownit.db` | SQLite path relative to the working directory |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | Allowed browser origin |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Set in `frontend/.env.local` if changing the API URL |

Restart the backend after changing its variables. Restart/rebuild Next.js after changing its public API URL. Tokens, local databases, build files and environments are ignored by Git.

Paste your key into the quoted string in the root `.env` file:

```dotenv
DARTMOUTH_API_KEY="PASTE_YOUR_DARTMOUTH_API_KEY_HERE"
```

The placeholder is treated as unconfigured, so Demo Mode continues to work before you add a key. The real key belongs only in the ignored `.env`, never in `.env.example`. Dartmouth lists the model IDs available to your account at its authenticated `/api/models` endpoint; see the [model-list instructions](https://rcweb.dartmouth.edu/~d20964h/2024-12-11-dartmouth-chat-api/model_list/).

## Demo walkthrough

1. Click **Open demo PR**. A simulated PR changes authorization and optimizes tag deduplication. It opens directly into its quiz; fixture data and rule-based grading are clearly labeled.
2. Inspect the relevant source snippet. Use Overview to see the PR diff and change-impact analysis if needed.
3. Answer the authorization question with `I do not know.` to see an incorrect outcome. The checkpoint stays blocked.
4. Click **Learn this concept**, ask about private documents, then click **Return & retest**.
5. Answer the new scenario, for example: `Deny a non-owner access to private documents; check public visibility and ownership.`
6. View **Report** for actual outcomes and before/after retest comparisons. There is no synthetic understanding percentage.
7. Answer every generated question, including followups and retests, and demonstrate every assessed concept correctly. The report's **Pass demo checkpoint** button remains disabled while gaps remain. An incorrect or uncertain answer cannot pass by merely finishing the quiz.
8. Restart the demo to try the same PR checkpoint again. Demo success never approves a real GitHub commit.

For independent teaching, open **Teaching**, select a concept or file, and ask a question. Switching views preserves answers and conversations. Recent reviews come from SQLite, including after restarting the server.

The fixtures are a small Python document-tag service: `auth.py` controls access, `service.py` filters documents, and `search.py` deduplicates tags. The initial authorization flaw is intentional. The modified version adds ownership checks and a set-based optimization. Demo teaching is prerecorded per concept, so repeated messages return the same explanation. Demo grading uses keyword groups, accepting two of three main-idea signals, and can misjudge prose; it is illustrative. Live grading accepts short, plain-language explanations when the essential idea is correct. Live mode uses model-generated interactions and never silently falls back to fixtures.

The website's demo always compares the initial fixture with the modified fixture, simulating a specific PR. The older initial-review fixture remains available through the demo API for testing.

## Real GitHub pull-request checkpoints

Set `DARTMOUTH_API_KEY` and an accessible `DARTMOUTH_MODEL`, then follow [GitHub checkpoint setup](docs/GITHUB_SETUP.md) for the server token, OAuth identity verification, signed webhook, and required branch check. Sign in as the PR author and enter a pull-request URL, or open the check's Details link directly from GitHub:

```text
https://github.com/owner/repository/pull/123
```

The checkpoint compares immutable PR base and head SHAs. The analyzer considers what changed, new subsystem structure, downstream effects, risks and regressions. Questions target the changed code. A new push gets a fresh assessment and cannot inherit an old revision's quiz answers. Publishing success requires a verified author session, correct assessment outcomes, and a final check that the PR is still open at the same base/head revision. Deleted-file patches appear in diffs; evidence links use available head files.

Live mode uses the [Dartmouth Chat Completions API](https://rcweb.dartmouth.edu/~d20964h/2024-12-11-dartmouth-chat-api/basic_usage/) with bearer-key authentication, and GitHub's [Git trees](https://docs.github.com/en/rest/git/trees) and [commit comparison](https://docs.github.com/en/rest/commits/commits) APIs. Every AI prompt includes the required JSON schema, and Pydantic validates the result. Provider-specific structured-output options are not assumed to work across Dartmouth's models; invalid output returns an actionable error. Three separate agent modules share one saved analysis. Question rubrics stay server-side. Evaluations include evidence and can be challenged after an attempt. Teaching does not count as passing.

## Tests and verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run lint
npm run typecheck
npm run build
cd ..
```

With the backend running:

```powershell
.\.venv\Scripts\python.exe scripts/smoke.py
```

The HTTP smoke test opens a demo PR, verifies that an attempted but incorrect quiz stays blocked, then checks teaching, a fresh retest, improvement reporting, successful completion and a new checkpoint with no inherited answers. Pytest uses isolated SQLite files under `.pytest-tmp`. Provider tests use mocks and spend no API credits. Tests cover signed webhooks, duplicate events, author identity, OAuth state/PKCE, cross-origin rejection, changed revisions, old-quiz rejection, failed status writes, incomplete code context, teaching/retests, persistence and completion rules.

## Source map

| Path | Responsibility |
| --- | --- |
| `ownit/models.py` | Typed request, analysis, question, tutor, review and report schemas |
| `ownit/github.py` | Public URL parsing, immutable snapshots and diffs |
| `ownit/agents/analysis.py` | Architecture and change analysis agent |
| `ownit/agents/testing.py` | Adaptive questions and evaluation agent |
| `ownit/changes.py` | Diff line mapping, changes-only assessment context and grounding checks |
| `ownit/agents/teaching.py` | Socratic tutoring agent |
| `ownit/llm.py` | Server-side Dartmouth Chat API adapter |
| `ownit/service.py` | Orchestration, transitions, evidence validation and reporting |
| `ownit/db.py` | SQLite review/session persistence |
| `ownit/security.py` | Credential redaction and file exclusions |
| `ownit/gates.py` | Pending/success GitHub statuses, revision binding, background jobs and stale-quiz rejection |
| `ownit/auth.py` | GitHub OAuth/PKCE and verified PR-author sessions |
| `docs/GITHUB_SETUP.md` | Required repository, webhook, identity and branch-protection setup |
| `ownit/demo.py`, `fixtures/` | Explicit offline fixtures and prerecorded interactions |
| `ownit/main.py` | FastAPI routes and CORS |
| `frontend/app/` | Next.js, React, TypeScript and Tailwind interface |
| `tests/`, `scripts/smoke.py` | Automated tests and running-server workflow checks |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health and live AI configuration status |
| GET | `/reviews` | Recent review history |
| POST | `/reviews` | Create a demo review; live reviews start through `/pull-requests` |
| GET | `/reviews/{id}` | Saved review, code and progress |
| POST | `/reviews/{id}/questions` | Generate questions once, then reuse |
| POST | `/reviews/{id}/answers` | Evaluate answer; `challenge: true` reconsiders an attempted answer |
| POST | `/reviews/{id}/teach` | Tutor message with concept/file and optional question |
| POST | `/reviews/{id}/retest` | New question for an attempted and taught concept |
| POST | `/reviews/{id}/complete` | Require all assessed concepts to pass; publish the live PR check if authorized |
| GET | `/reviews/{id}/report` | Outcomes, gaps, teaching and retest comparisons |
| POST | `/pull-requests` | Author-authenticated PR checkpoint creation |
| GET | `/pull-requests/{id}` | Public progress and PR metadata, without private answers/rubrics |
| POST | `/pull-requests/{id}/retry` | Author-only retry after analysis failure |
| POST | `/webhooks/github` | Signed GitHub PR events; queues revision-specific analysis |
| GET | `/auth/github`, `/auth/github/callback`, `/auth/me` | GitHub identity verification and session state |

## Scope and limitations

- This is a single-process MVP. Real PR quizzes require GitHub OAuth identity matching the author. Demo sessions remain unauthenticated and cannot write GitHub statuses. Repository setup and a required branch check are necessary for remote merge enforcement; no remote GitHub configuration was changed automatically.
- GitHub context is bounded: at most 25 supported text files, 24 KB per file and 90 KB total, prioritizing changed files; diffs are capped at 35 KB. Live checkpoints stop if supported changed source or its patches cannot fit in context, or the comparison is truncated. Surrounding repository context is sampled and limitations remain visible. This is advisory, not an exhaustive audit.
- Repository code is never executed. Sensitive filenames are excluded; recognizable credential patterns and configured tokens are redacted. Prompts treat code and user text as untrusted data. Pattern matching cannot guarantee recognition of every secret format; review public source before submitting it.
- Each Dartmouth AI request has a 120-second timeout. Provider failures return actionable errors and preserve previously saved state. Mutations are serialized in-process; multiple Uvicorn workers are outside MVP scope.
- Small PRs normally get 2–4 concise questions, with fewer for tiny changes and up to 7 for distinct complex additions. Each question focuses on one central idea in NEW or modified code. Unchanged code is context, never an independent PR quiz topic. The tester receives changed-line snippets instead of full original files; generated questions and retests must cite changed head lines. Plain-language, brief answers pass when their central reasoning is right; specialist terminology, Big-O notation, exhaustive edge cases and optional rubric details are not required unless essential to the asked change. Material mistakes and uncertain judgments still block the checkpoint. After teaching, new retests can close the same concept's gap. An unanswered retest is reused instead of generating duplicates.
- Completion now requires a latest correct evaluation for every originally assessed concept and attempts on all generated questions. Teaching alone cannot pass. Earlier incorrect attempts remain visible in reports after a successful retest. Completed sessions are immutable; migrated historical sessions do not approve new live checkpoints.
- New quizzes and retests use the concise, changes-only question policy; existing saved questions and answers remain in history. New answer evaluations and challenges use the more forgiving main-idea grading policy. To try a fresh assessment, restart the demo PR or submit a new PR revision.
- Live Dartmouth checks with public demo code verified change-grounded, concise question generation, acceptance of brief correct explanations, and rejection of a material authorization mistake. Automated provider tests use mocks. Model IDs and access still depend on the Dartmouth account. The HTTP smoke test verifies the core demo workflow. Native Chrome UI verification was blocked by the computer-use runtime's URL safety check; frontend verification used lint, typecheck, production build and an HTTP page check.
