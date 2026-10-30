import base64
import re
from urllib.parse import urlparse, quote
import httpx
from fastapi import HTTPException
from .security import redact, safe_path

MAX_FILE = 24000
MAX_CONTEXT = 90000
EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".md", ".toml", ".json", ".yml", ".yaml", ".sql")


def parse_url(url: str):
    parsed = urlparse(url)
    match = re.fullmatch(r"/([\w.-]+)/([\w.-]+?)(?:/pull/([1-9]\d*))?/?", parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment or not match:
        raise HTTPException(422, "Use https://github.com/owner/repo or https://github.com/owner/repo/pull/123")
    owner, repo, pr = match.groups()
    repo = repo.removesuffix(".git")
    if owner in {".", ".."} or repo in {"", ".", ".."}:
        raise HTTPException(422, "Invalid repository")
    return f"{owner}/{repo}".lower(), int(pr) if pr else None


class GitHub:
    def __init__(self, token=None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30)

    def close(self):
        self.client.close()

    def get(self, path):
        try:
            r = self.client.get(path)
        except httpx.HTTPError:
            raise HTTPException(502, "Could not reach GitHub. Try Demo Mode or retry.") from None
        if r.status_code == 404:
            raise HTTPException(404, "Public repository, commit, or pull request not found.")
        if r.status_code in (403, 429):
            raise HTTPException(429, "GitHub access denied or rate limit reached. Retry later or configure GITHUB_TOKEN.")
        if not r.is_success:
            raise HTTPException(502, "GitHub request failed.")
        return r.json()

    def fetch(self, repo, pr, commit, baseline):
        metadata = self.get(f"/repos/{repo}")
        if metadata.get("private") or metadata.get("visibility", "public") != "public":
            raise HTTPException(422, "Only public repositories are supported.")
        base = baseline
        if pr:
            pull = self.get(f"/repos/{repo}/pulls/{pr}")
            base, sha = pull["base"]["sha"], pull["head"]["sha"]
        else:
            sha = self.get(f"/repos/{repo}/commits/{quote(commit or metadata['default_branch'], safe='')}")["sha"]
        tree = self.get(f"/repos/{repo}/git/trees/{sha}?recursive=1")
        warnings = ["Context is sampled: at most 25 files, 24 KB per file and 90 KB total. Findings are advisory."]
        if tree.get("truncated"):
            warnings.append("GitHub truncated the repository tree; some components may be missing.")
        changes, diff = [], ""
        if base:
            comparison = self.get(f"/repos/{repo}/compare/{base}...{sha}")
            changes = comparison.get("files", [])
            diff = redact("\n".join(f"{f['status']} {f['filename']}\n{f.get('patch', '[Patch unavailable or binary]')}" for f in changes if safe_path(f['filename'])))[:35000]
            if comparison.get("total_commits", 0) > 250 or len(changes) >= 300:
                warnings.append("Comparison may be truncated by GitHub limits.")
        changed = {f["filename"] for f in changes}
        candidates = [f for f in tree.get("tree", []) if f["type"] == "blob" and f.get("size", MAX_FILE + 1) <= MAX_FILE and safe_path(f["path"]) and f["path"].endswith(EXTENSIONS)]
        candidates.sort(key=lambda f: (f['path'] not in changed, f['path'].count('/'), f['path']))
        files, total = {}, 0
        for f in candidates[:25]:
            if total + f.get("size", 0) > MAX_CONTEXT:
                continue
            blob = self.get(f"/repos/{repo}/git/blobs/{f['sha']}")
            if blob.get("encoding") != "base64" or blob.get("size", MAX_FILE + 1) > MAX_FILE:
                continue
            content = redact(base64.b64decode(blob["content"]).decode("utf-8", errors="replace"))
            files[f['path']] = content
            total += len(content)
        if not files:
            raise HTTPException(422, "No supported text files within the context limits.")
        return {"sha": sha, "base_sha": base, "files": files, "diff": diff, "changed_files": sorted(changed), "limitations": warnings}
