"""GitHub integration using official GitHub CLI; credentials stay in OS credential storage."""
from __future__ import annotations
import base64, json, re, shutil, subprocess
from urllib.parse import quote
from pathlib import Path

_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MAX_UPLOAD = 2 * 1024 * 1024

def _gh_exe():
    found = shutil.which("gh")
    if found: return found
    candidate = Path("C:/Program Files/GitHub CLI/gh.exe")
    return str(candidate) if candidate.is_file() else None

def _gh(*args, input_text=None, timeout=45):
    exe = _gh_exe()
    if not exe:
        return False, "GitHub CLI is not installed. Use Connect GitHub in JARVIS settings."
    try:
        p = subprocess.run([exe, *map(str, args)], input=input_text, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, "GitHub did not respond before timeout."
    except Exception as exc:
        return False, str(exc)
    return p.returncode == 0, (p.stdout or p.stderr or "").strip()

def _status():
    ok, detail = _gh("auth", "status", "--hostname", "github.com")
    if not ok:
        return False, detail
    ok, user = _gh("api", "user", "--jq", ".login")
    return True, f"Connected to GitHub as @{user}." if ok else detail

def _connect(_values=None):
    exe = _gh_exe()
    if not exe:
        winget = shutil.which("winget")
        if not winget:
            return "Install the official GitHub CLI from https://cli.github.com/, then reopen JARVIS."
        try:
            subprocess.Popen([winget, "install", "--id", "GitHub.cli", "--exact",
                "--accept-package-agreements", "--accept-source-agreements"],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            return "GitHub CLI installer started. Finish installation, reopen JARVIS, then click Connect GitHub again."
        except Exception as exc:
            return f"Could not start installation: {exc}"
    ok, detail = _status()
    if ok:
        return detail
    try:
        subprocess.Popen([exe, "auth", "login", "--hostname", "github.com",
            "--git-protocol", "https", "--web"],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return "GitHub device sign-in opened. Complete authorization in the browser, then click Connect GitHub again."
    except Exception as exc:
        return f"Could not start GitHub sign-in: {exc}"

def _upload(repo, local_path, remote_path, message, branch=""):
    if not _REPO.fullmatch(repo or ""):
        return "Repository must be owner/name."
    remote_path = (remote_path or "").strip().replace("\\", "/").strip("/")
    if not remote_path or any(x in ("", ".", "..") for x in remote_path.split("/")):
        return "Invalid destination path."
    source = Path(local_path).expanduser()
    if source.is_symlink():
        return "Symbolic links are refused."
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError):
        return "Selected file does not exist."
    if not source.is_file() or source.stat().st_size > _MAX_UPLOAD:
        return "Select a regular file up to 2 MB."
    endpoint = f"repos/{repo}/contents/{quote(remote_path, safe='/')}"
    payload = {"message": (message or f"Add {source.name}")[:200],
               "content": base64.b64encode(source.read_bytes()).decode("ascii")}
    if branch:
        payload["branch"] = branch
    exists, result = _gh("api", endpoint)
    if exists:
        try:
            payload["sha"] = json.loads(result)["sha"]
        except (ValueError, KeyError, TypeError):
            return "Could not read existing file SHA; upload cancelled."
    elif "404" not in result and "Not Found" not in result:
        return f"Could not inspect GitHub destination: {result[:300]}"
    ok, result = _gh("api", endpoint, "--method", "PUT", "--input", "-",
                     input_text=json.dumps(payload), timeout=60)
    if not ok:
        return f"GitHub upload failed: {result[:500]}"
    try:
        url = json.loads(result).get("content", {}).get("html_url", "")
    except ValueError:
        url = ""
    return f"Uploaded {source.name} to {repo}/{remote_path}. {url}".strip()

PLUGIN = {
    "name": "github_account",
    "description": ("Connect to GitHub through the official GitHub CLI. Check account status, list repositories, "
        "and upload the file selected in JARVIS. Uploads require an on-screen user confirmation; never claim "
        "a write succeeded until GitHub confirms it."),
    "tier": "extra",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "list_repos", "upload_file"]},
        "repo": {"type": "STRING", "description": "GitHub owner/repository."},
        "remote_path": {"type": "STRING", "description": "Destination path in the repository."},
        "message": {"type": "STRING", "description": "Commit message."},
        "branch": {"type": "STRING", "description": "Optional existing branch."}
    }, "required": ["action"]}
}
PLUGIN_SETTINGS = {"namespace": "github_account", "title": "GitHub account",
    "fields": [], "action": {"label": "INSTALL / CONNECT / CHECK GITHUB", "run": _connect}}

def run(parameters, player=None, session_memory=None):
    action = str(parameters.get("action", "status")).lower().strip()
    ok, status = _status()
    if not ok:
        return "GitHub is not connected. Open Settings > Plugin Settings > GitHub and click Connect GitHub. " + status[:250]
    if action == "status":
        return status
    if action == "list_repos":
        ok, result = _gh("repo", "list", "--limit", "30", "--json",
                         "nameWithOwner,url,visibility,description")
        if not ok:
            return f"Could not list repositories: {result[:400]}"
        try:
            rows = json.loads(result)
            return "GitHub repositories:\n" + "\n".join(
                f"- {x.get('nameWithOwner')} ({x.get('visibility')}) {x.get('url')}" for x in rows[:30])
        except ValueError:
            return result[:2500]
    if action == "upload_file":
        if player is None:
            return "Select/drop the file in JARVIS before uploading."
        selected = getattr(player, "current_file", None)
        if callable(selected):
            selected = selected()
        if not selected:
            return "Select/drop the file in JARVIS before uploading."
        repo = str(parameters.get("repo", "")).strip()
        dest = str(parameters.get("remote_path", "")).strip()
        if not repo or not dest:
            return "Provide repo (owner/name) and remote_path."
        from core import confirm
        return confirm.request(key="github-upload-file", title="Upload file to GitHub?",
            detail=f"Repository: {repo}\nDestination: {dest}\nFile: {Path(str(selected)).name}\nThis creates a commit.",
            run=lambda: _upload(repo, str(selected), dest,
                str(parameters.get("message", "")).strip(), str(parameters.get("branch", "")).strip()),
            wait_for_result=True)
    return "Unknown action. Use status, list_repos or upload_file."
