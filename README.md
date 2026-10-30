# OwnIt

**AI understands your code. But do you?**

OwnIt (`defend-your-pr`) is a hackathon MVP for understanding public GitHub code through analysis, adaptive testing, and Socratic teaching. It supports initial reviews, commit/PR change reviews, independent teaching, and Test → Teach → Retest → Understanding Report.

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
| `GITHUB_TOKEN` | empty | Optional GitHub REST token for higher rate limits; public repos only |
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

1. Click **Open demo**. Demo analysis, scripted teaching, and keyword-based grading are clearly labeled.
2. Inspect architecture, authorization risks, algorithms, data flow, and expandable line references.
3. Click **Start testing**. Answer the authorization question with `I do not know.` to see an incorrect outcome.
4. Click **Learn this concept**, ask about private documents, then click **Return & retest**.
5. Answer the new scenario, for example: `Deny a non-owner access to private documents; check public visibility and ownership.`
6. View **Report** for actual outcomes and before/after retest comparisons. There is no synthetic understanding percentage.
7. Answer every generated question, including followups and retests, then **Complete review**. Completion records a fully attempted assessment; remaining gaps stay in the report.
8. Click **Analyze modified version** to compare against the completed fixture. The diff fixes ownership checks and replaces repeated list membership with a set while preserving output order.

For independent teaching, open **Teaching**, select a concept or file, and ask a question. Switching views preserves answers and conversations. Recent reviews come from SQLite, including after restarting the server.

The fixtures are a small Python document-tag service: `auth.py` controls access, `service.py` filters documents, and `search.py` deduplicates tags. The initial authorization flaw is intentional. The modified version adds ownership checks and a set-based optimization. Demo teaching is prerecorded per concept, so repeated messages return the same explanation. Demo grading matches three keyword groups and can misjudge prose; it is illustrative. Live mode uses model-generated interactions and never silently falls back to fixtures.

Opening the initial demo fixture restarts its walkthrough as an initial review. The modified fixture uses the most recent completed demo review as its comparison baseline.

## Real GitHub reviews

Set `DARTMOUTH_API_KEY` in `.env`, choose an accessible `DARTMOUTH_MODEL` if needed, optionally set `GITHUB_TOKEN`, restart the backend, and enter either:

```text
https://github.com/owner/repository
https://github.com/owner/repository/pull/123
```

The optional commit field accepts a 7–40 character hexadecimal SHA. Repository reviews resolve the default branch or selected commit to an immutable SHA. Only a **completed** review becomes the baseline for future change reviews. PR reviews always compare the PR base and head. The analyzer considers new subsystem structure, downstream effects, risks and regressions. Deleted-file patches appear in diffs; evidence links use available head files.

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

The HTTP smoke test creates local demo reviews and checks initial review, incorrect answer, teaching, a new retest, improvement reporting, completion, change review, and independent teaching. Pytest uses isolated SQLite files under `.pytest-tmp`. LLM and GitHub tests use mocked provider responses and spend no API credits. Tests cover URL validation, initial/change selection, strict AI schemas, questions, evaluations, teaching transitions, retests, persistence, challenges, completion, secret redaction and errors.

## Source map

| Path | Responsibility |
| --- | --- |
| `ownit/models.py` | Typed request, analysis, question, tutor, review and report schemas |
| `ownit/github.py` | Public URL parsing, immutable snapshots and diffs |
| `ownit/agents/analysis.py` | Architecture and change analysis agent |
| `ownit/agents/testing.py` | Adaptive questions and evaluation agent |
| `ownit/agents/teaching.py` | Socratic tutoring agent |
| `ownit/llm.py` | Server-side Dartmouth Chat API adapter |
| `ownit/service.py` | Orchestration, transitions, evidence validation and reporting |
| `ownit/db.py` | SQLite review/session persistence |
| `ownit/security.py` | Credential redaction and file exclusions |
| `ownit/demo.py`, `fixtures/` | Explicit offline fixtures and prerecorded interactions |
| `ownit/main.py` | FastAPI routes and CORS |
| `frontend/app/` | Next.js, React, TypeScript and Tailwind interface |
| `tests/`, `scripts/smoke.py` | Automated tests and running-server workflow checks |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health and live AI configuration status |
| GET | `/reviews` | Recent review history |
| POST | `/reviews` | Create and analyze GitHub or demo review |
| GET | `/reviews/{id}` | Saved review, code and progress |
| POST | `/reviews/{id}/questions` | Generate questions once, then reuse |
| POST | `/reviews/{id}/answers` | Evaluate answer; `challenge: true` reconsiders an attempted answer |
| POST | `/reviews/{id}/teach` | Tutor message with concept/file and optional question |
| POST | `/reviews/{id}/retest` | New question for an attempted and taught concept |
| POST | `/reviews/{id}/complete` | Finalize fully attempted assessment and set baseline |
| GET | `/reviews/{id}/report` | Outcomes, gaps, teaching and retest comparisons |

## Scope and limitations

- This is a single-process local application with a demo identity and no authentication. Bind to loopback. Add authentication, request budgets and job orchestration before multi-user hosting.
- GitHub context is sampled: at most 25 supported text files, 24 KB per file and 90 KB total, prioritizing changed files; diffs are capped at 35 KB. Truncation and review limits are disclosed in analysis. This is advisory, not an exhaustive audit.
- Repository code is never executed. Sensitive filenames are excluded; recognizable credential patterns and configured tokens are redacted. Prompts treat code and user text as untrusted data. Pattern matching cannot guarantee recognition of every secret format; review public source before submitting it.
- Each Dartmouth AI request has a 120-second timeout. Provider failures return actionable errors and preserve previously saved state. Mutations are serialized in-process; multiple Uvicorn workers are outside MVP scope.
- Assessments normally have 3–7 questions; tiny documentation scopes may have fewer. Partial answers get targeted followups, incorrect answers can move to tutoring, uncertain judgments remain uncertain. One new retest is available per original question after teaching.
- Completed sessions are immutable. A completed assessment may still contain knowledge gaps; completion and demonstrated understanding are distinct.
- Live Dartmouth calls were not exercised without credentials. Provider paths were verified with mocked model/HTTP responses. The default requests Claude Sonnet 5.5 using `anthropic.claude-sonnet-5-5`; Dartmouth's authenticated model list must confirm the exact ID and account access. The HTTP smoke test verifies all four core demo workflows. Native Chrome UI verification was blocked by the computer-use runtime's URL safety check; frontend verification used lint, typecheck, production build and an HTTP page check.
