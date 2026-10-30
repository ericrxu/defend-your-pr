import os
import re


def redact(text: str) -> str:
    for key in ("DARTMOUTH_API_KEY", "GITHUB_TOKEN"):
        secret = os.getenv(key)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", lambda m: "[REDACTED PRIVATE KEY]" + '\n' * m.group().count('\n'), text, flags=re.S)
    text = re.sub(r'''(?i)((?:api[_-]?key|password|secret(?:[_-]?key)?|token)['"]?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)''', r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(https?://)[^\s/:]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    return re.sub(r"\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{15,}|github_pat_[\w]+|AKIA[A-Z0-9]{16}|eyJ[\w-]+\.[\w-]+\.[\w-]+)\b", "[REDACTED]", text)


def safe_path(path: str) -> bool:
    parts = path.lower().split("/")
    return not any(p in {".git", "node_modules", "vendor", "dist", ".venv", "__pycache__"} for p in parts) and not any(s in path.lower() for s in (".env", ".pem", ".key", ".npmrc", ".pypirc", "credentials", "secret", "lock.json", "package-lock", "yarn.lock", "pnpm-lock"))


def scrub(value):
    """Redact values before serialization so redaction cannot corrupt JSON syntax."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    return value
