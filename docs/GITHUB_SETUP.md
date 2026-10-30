# Connect the pull-request merge checkpoint

OwnIt now implements this workflow:

**Open/update PR → pending GitHub check → author signs in → quiz about the diff → teach/retest if needed → pass check for that revision → merge becomes eligible.**

Running the website alone does not block GitHub. The repository must require the OwnIt status check as described below. This setup is for public repositories.

## 1. Configure the backend

Keep your existing Dartmouth key and model settings. Add these to the ignored root `.env`:

```dotenv
GITHUB_TOKEN=YOUR_SERVER_TOKEN
OWNIT_REPOSITORIES=your-user/your-repo
GITHUB_WEBHOOK_SECRET=YOUR_RANDOM_WEBHOOK_SECRET
GITHUB_CLIENT_ID=YOUR_OAUTH_APP_CLIENT_ID
GITHUB_CLIENT_SECRET=YOUR_OAUTH_APP_CLIENT_SECRET
OWNIT_APP_URL=http://localhost:3000
OWNIT_API_URL=http://localhost:8000
FRONTEND_ORIGIN=http://localhost:3000
```

`OWNIT_REPOSITORIES` accepts a comma-separated list of allowed `owner/repo` names. The server refuses other repositories, including when a webhook is signed correctly.

Use a fine-grained GitHub personal access token restricted to the connected repositories, with **Contents: read** and **Commit statuses: read/write**. This token belongs to the service, stays server-side, and posts the required status. The backend never merges the PR itself. GitHub documents the [commit-status API and token permissions](https://docs.github.com/en/rest/commits/statuses#create-a-commit-status).

Choose a long random webhook secret and use the same value in GitHub and `.env`. Requests are validated with HMAC-SHA256 before processing, following [GitHub's webhook verification guidance](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).

## 2. Create an OAuth App to identify the PR author

In GitHub developer settings, create an OAuth App:

- Homepage URL: the frontend's `OWNIT_APP_URL`.
- Authorization callback URL: `OWNIT_API_URL/auth/github/callback`.
- For local development: `http://localhost:8000/auth/github/callback`.

Copy its client ID and client secret to the backend settings. OwnIt requests only `read:user` identity access. The author logs in through GitHub; OwnIt compares the verified numeric GitHub user ID to the PR author ID. OAuth state and PKCE protect sign-in. The transient OAuth access token is discarded after `/user` is read. Only a hashed, expiring session identifier and the verified identity are stored in SQLite.

This is separate from the server token used to publish checks. The author's OAuth token does not grant the application permission to merge or modify repository content. See [GitHub's OAuth flow](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps).

## 3. Give GitHub a reachable webhook address

GitHub cannot deliver a webhook to your computer's `localhost`. Use a reachable HTTPS deployment or a development tunnel for the backend, and a frontend address reachable by the person taking the quiz.

Set the real addresses in `OWNIT_APP_URL`, `OWNIT_API_URL`, and `FRONTEND_ORIGIN`. Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to the backend's public address, then restart/rebuild the frontend. Use frontend/API hosts on the same site so the HTTP-only SameSite cookie can be sent. HTTPS API addresses enable secure cookies.

For local manual testing, OAuth and the website can use localhost. Automatic GitHub delivery still requires a public webhook route. Use one Uvicorn process for this MVP.

## 4. Register the repository webhook

In the connected repository's **Settings → Webhooks**, add:

- Payload URL: `OWNIT_API_URL/webhooks/github`.
- Content type: `application/json`.
- Secret: the same `GITHUB_WEBHOOK_SECRET`.
- Events: **Pull requests**.
- Active: enabled.

OwnIt handles opened, reopened, new-commit (`synchronize`), ready-for-review, and base-change events. A push to an existing PR emits `synchronize`; a separate push-event hook is unnecessary. Webhooks persist a job before analysis. Duplicate deliveries reuse the same revision's quiz. Queued/interrupted analysis is recovered after restart; failed analysis can be retried by the author.

The check's **Details** link opens `OWNIT_APP_URL/?job=...`. It shows analysis progress, offers GitHub sign-in, and opens the quiz once ready.

## 5. Require the check before merging

In the target branch's protection rule or ruleset:

1. Require a pull request before merging.
2. Require status checks to pass.
3. Add the exact status context **`OwnIt / understanding`**. Open a sample PR first if GitHub needs to discover the check.
4. Require the branch to be up to date before merging. This prevents an assessment for an older base revision from satisfying the current branch's merge requirements.
5. Apply the rule to the intended actors, including administrators if they should be blocked; remove unwanted bypass permissions.

The check stays pending while the quiz is unanswered, incorrect, partial, uncertain, or unavailable. Teaching alone never passes it. After all generated questions are attempted and every assessed concept has a latest correct evaluation, **Pass check on GitHub** rechecks the PR author, open state, head SHA, and base SHA before publishing success. If GitHub refuses the status write, OwnIt does not mark the checkpoint passed.

GitHub enforces these rules, not the local website. See [required status checks and branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## 6. Verify with a real PR

1. Open a small PR in the connected public repository.
2. Confirm **OwnIt / understanding** is pending and merging is blocked.
3. Open **Details**, sign in as the PR author, and answer a question incorrectly. Confirm the check remains pending.
4. Use teaching and a new retest; demonstrate all assessed concepts correctly.
5. Open the report and select **Pass check on GitHub**. Confirm that the status succeeds. Other GitHub checks and reviews still apply.
6. Push another commit. Confirm a new pending checkpoint with fresh questions appears. The old quiz cannot approve the new SHA.

## MVP boundaries

- Demo checkpoints simulate blocking and never write GitHub statuses. Live author identity is mandatory; the demo identity cannot approve a real PR.
- The check attests to the assessed concepts for the exact revision. LLM judgments are fallible and can be challenged; this is not a guarantee of complete human understanding or code correctness.
- Commit statuses are SHA-scoped on GitHub. This MVP assumes one active PR per head SHA; independent authors should use distinct branches/commits. Reusing the identical head commit across separate PRs can share a GitHub status, even though OwnIt quiz sessions and author checks are separate.
- Analysis is bounded, as described in the README. A live checkpoint refuses approval when supported changed source or its diff cannot be included within the limits. Split oversized PRs into smaller changes. Surrounding repository context is still sampled, with its limitations displayed.
- No real GitHub webhook, OAuth account or branch rule was configured by the implementation session. Automated tests mock GitHub and Dartmouth. A maintainer must perform the setup above to enable actual remote merge blocking.
