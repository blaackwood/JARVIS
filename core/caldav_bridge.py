"""Private CalDAV projection of JARVIS reminders for Apple Reminders.

Radicale is bound to loopback only. The main JARVIS HTTPS listener proxies
/dav/* to it after TLS termination. The routines store remains canonical.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo
import requests
import xml.etree.ElementTree as ET

DAV_NS = "DAV:"
COLLECTION = "JARVIS"
USERNAME = "jarvis"
LISTEN_HOST = "127.0.0.1"
DEFAULT_PORT = 5232
SCRIPT_NAME = "/dav"
SYNC_SECONDS = 30
MAX_ITEM_BYTES = 256_000


def _escape_ical(value: str) -> str:
    return (str(value or "").replace("\\", "\\\\").replace("\r\n", "\\n")
            .replace("\n", "\\n").replace("\r", "\\n")
            .replace(";", "\\;").replace(",", "\\,"))


def _unescape_ical(value: str) -> str:
    out, escaped = [], False
    for ch in value:
        if escaped:
            out.append("\n" if ch in "nN" else ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        else:
            out.append(ch)
    if escaped:
        out.append("\\")
    return "".join(out)


def _fold_ical(line: str) -> str:
    chunks, current, width = [], [], 0
    for ch in line:
        size = len(ch.encode("utf-8"))
        if width + size > 70:
            chunks.append("".join(current))
            current, width = [" "], 1
        current.append(ch)
        width += size
    chunks.append("".join(current))
    return "\r\n".join(chunks)


def _format_utc(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_ical_datetime(raw: str, params: dict | None = None):
    raw = str(raw or "").strip()
    params = params or {}
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", raw):
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            return None
    value = raw.rstrip("Z").replace("-", "").replace(":", "")
    fmt = "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M"
    try:
        dt = datetime.strptime(value[:len(datetime.now().strftime(fmt))], fmt)
    except ValueError:
        return None
    if raw.endswith("Z"):
        return dt.replace(tzinfo=timezone.utc)
    tzid = params.get("TZID")
    if tzid:
        try:
            return dt.replace(tzinfo=ZoneInfo(tzid))
        except Exception:
            pass
    try:
        from core.cloud import user_tz
        return dt.replace(tzinfo=user_tz())
    except Exception:
        return dt.astimezone()


def _property_map(ics: str) -> dict:
    raw_lines = str(ics or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for line in raw_lines:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        elif line:
            lines.append(line)
    in_todo, props = False, {}
    for line in lines:
        if line.upper() == "BEGIN:VTODO":
            in_todo = True
            continue
        if line.upper() == "END:VTODO":
            break
        if not in_todo or ":" not in line:
            continue
        left, value = line.split(":", 1)
        bits = left.split(";")
        name, params = bits[0].upper(), {}
        for bit in bits[1:]:
            if "=" in bit:
                k, v = bit.split("=", 1)
                params[k.upper()] = v.strip('"')
        props.setdefault(name, []).append((value, params))
    return props


def parse_vtodo(ics: str) -> dict | None:
    props = _property_map(ics)
    if not props:
        return None

    def value(name, default=""):
        rows = props.get(name) or []
        return _unescape_ical(rows[0][0]) if rows else default

    uid = value("UID").strip()
    summary = value("SUMMARY").strip()
    if not uid or not summary:
        return None
    due_rows = props.get("DUE") or props.get("DTSTART") or []
    due = _parse_ical_datetime(due_rows[0][0], due_rows[0][1]) if due_rows else None
    due_ts = due.timestamp() if isinstance(due, datetime) else None
    status = value("STATUS", "NEEDS-ACTION").upper()
    status = {"COMPLETED": "done", "CANCELLED": "cancelled",
              "NEEDS-ACTION": "open", "IN-PROCESS": "open"}.get(status, "open")
    last_rows = props.get("LAST-MODIFIED") or props.get("DTSTAMP") or []
    modified = _parse_ical_datetime(last_rows[0][0], last_rows[0][1]) if last_rows else None
    modified_ts = modified.timestamp() if isinstance(modified, datetime) else 0.0
    return {"uid": uid, "message": summary[:200], "due_ts": due_ts,
            "status": status, "modified_ts": modified_ts,
            "description": value("DESCRIPTION")[:2000],
            "date_only": isinstance(due, date) and not isinstance(due, datetime)}


def serialize_vtodo(item: dict) -> str:
    now = _format_utc(time.time())
    status = {"open": "NEEDS-ACTION", "done": "COMPLETED",
              "cancelled": "CANCELLED", "missed": "COMPLETED"}.get(
                  str(item.get("status") or "open"), "NEEDS-ACTION")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JARVIS//Apple Reminders//EN",
        "CALSCALE:GREGORIAN", "BEGIN:VTODO",
        "UID:" + _escape_ical(item["uid"]), "DTSTAMP:" + now,
        "LAST-MODIFIED:" + now,
        "SUMMARY:" + _escape_ical(item.get("message") or "JARVIS reminder"),
        "DUE:" + _format_utc(float(item["due_ts"])), "STATUS:" + status,
    ]
    if item.get("description"):
        lines.append("DESCRIPTION:" + _escape_ical(item["description"]))
    if status == "COMPLETED":
        lines.append("COMPLETED:" + now)
    lines += ["END:VTODO", "END:VCALENDAR"]
    return "\r\n".join(_fold_ical(line) for line in lines) + "\r\n"


def _payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _remote_payload(parsed: dict) -> dict:
    return {k: parsed.get(k) for k in ("message", "due_ts", "status", "description")}


def _local_payload(routine: dict, meta: dict) -> dict:
    due_ts = meta.get("due_ts") if "due_ts" in meta else routine.get("next_ts")
    return {"message": str(routine.get("text") or meta.get("message") or "")[:200],
            "due_ts": float(due_ts or 0),
            "status": str(meta.get("status") or "open"),
            "description": str(meta.get("description") or "")[:2000]}


class CalDAVBridge:
    """Own one private Radicale process and reconcile its VTODO collection."""

    def __init__(self, runtime, port: int = DEFAULT_PORT):
        self.runtime = runtime
        self.state = runtime.state
        self.port = int(port)
        self.base = f"http://{LISTEN_HOST}:{self.port}"
        self.storage = self.state.dir / "caldav"
        self.config_path = self.state.dir / "radicale.conf"
        self.users_path = self.state.dir / "radicale.users"
        self.log_path = self.state.dir / "radicale.log"
        from core.cloud import _Doc
        self.auth_doc = _Doc(self.state.dir / "caldav_auth.json", {})
        self._process = None
        self._log_handle = None
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._password = self._load_password()

    def _load_password(self) -> str:
        doc = self.auth_doc.read()
        password = str(doc.get("password") or "")
        token = str(doc.get("setup_token") or "")
        if len(password) < 24 or len(token) < 32:
            password = password if len(password) >= 24 else secrets.token_urlsafe(32)
            token = token if len(token) >= 32 else secrets.token_urlsafe(40)
            saved = dict(doc)
            saved.update({"username": USERNAME, "password": password,
                          "setup_token": token, "created_at": saved.get("created_at") or time.time()})
            self.auth_doc.update(lambda d: (d.clear(), d.update(saved)))
        self.setup_token = token
        return password

    def _write_config(self) -> None:
        import bcrypt
        self.storage.mkdir(parents=True, exist_ok=True)
        hashed = bcrypt.hashpw(self._password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
        self.users_path.write_text(f"{USERNAME}:{hashed}\n", encoding="utf-8")
        try:
            self.users_path.chmod(0o600)
        except OSError:
            pass
        config = (
            "[server]\n"
            f"hosts = {LISTEN_HOST}:{self.port}\n"
            f"script_name = {SCRIPT_NAME}\n"
            "timeout = 60\nmax_connections = 8\n"
            "max_content_length = 2000000\nmax_resource_size = 256000\n"
            "[auth]\ntype = htpasswd\n"
            f"htpasswd_filename = {self.users_path}\n"
            "htpasswd_encryption = bcrypt\ndelay = 1\n"
            "[rights]\ntype = owner_only\n"
            "[storage]\ntype = multifilesystem\n"
            f"filesystem_folder = {self.storage / 'collections'}\n"
            "[logging]\nlevel = warning\nmask_passwords = True\n"
        )
        self.config_path.write_text(config, encoding="utf-8")
        try:
            self.config_path.chmod(0o600)
            self.storage.chmod(0o700)
        except OSError:
            pass

    def _dav(self, method: str, path: str, body: bytes | str | None = None,
             headers: dict | None = None, timeout: float = 15):
        data = body.encode("utf-8") if isinstance(body, str) else body
        hdrs = {"X-Script-Name": SCRIPT_NAME}
        hdrs.update(headers or {})
        return requests.request(method, self.base + path, data=data, headers=hdrs,
                                auth=(USERNAME, self._password), timeout=timeout)

    def _ensure_collection(self) -> None:
        probe = self._dav("PROPFIND", f"/{USERNAME}", b'<?xml version="1.0"?>'
            b'<d:propfind xmlns:d="DAV:"><d:allprop/></d:propfind>',
            {"Depth": "0", "Content-Type": "application/xml"})
        if probe.status_code != 207:
            raise RuntimeError(f"CalDAV principal check failed ({probe.status_code}).")
        path = f"/{USERNAME}/{COLLECTION}"
        check = self._dav("PROPFIND", path + "/", b'<?xml version="1.0"?>'
            b'<d:propfind xmlns:d="DAV:"><d:allprop/></d:propfind>',
            {"Depth": "0", "Content-Type": "application/xml"})
        if check.status_code == 207:
            return
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            '<create xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav" '
            'xmlns:I="http://apple.com/ns/ical/"><set><prop>'
            '<resourcetype><collection/><C:calendar/></resourcetype>'
            '<C:supported-calendar-component-set><C:comp name="VTODO"/></C:supported-calendar-component-set>'
            '<displayname>JARVIS</displayname>'
            '<C:calendar-description>JARVIS Reminders</C:calendar-description>'
            '<I:calendar-color>#007affff</I:calendar-color>'
            '</prop></set></create>'
        )
        created = self._dav("MKCOL", path, xml, {"Content-Type": "application/xml"})
        if created.status_code not in (201, 405, 409):
            raise RuntimeError(f"Could not create the JARVIS CalDAV list ({created.status_code}).")
        verify = self._dav("PROPFIND", path + "/", b'<?xml version="1.0"?>'
            b'<d:propfind xmlns:d="DAV:"><d:allprop/></d:propfind>',
            {"Depth": "0", "Content-Type": "application/xml"})
        if verify.status_code != 207:
            raise RuntimeError("The JARVIS CalDAV list was not discoverable after creation.")

    def start(self) -> bool:
        if self._process is not None and self._process.poll() is None:
            return True
        self._write_config()
        self._log_handle = self.log_path.open("ab")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self._process = subprocess.Popen(
            [sys.executable, "-m", "radicale", "--config", str(self.config_path)],
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=self._log_handle, stderr=subprocess.STDOUT, creationflags=flags,
        )
        deadline = time.monotonic() + 15
        last_error = None
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self.stop()
                raise RuntimeError("The CalDAV service exited during startup; inspect cloud_state/radicale.log.")
            try:
                self._ensure_collection()
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.25)
        else:
            self.stop()
            raise RuntimeError(f"CalDAV did not become ready: {last_error}")
        self._stop.clear()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._sync_loop, name="jarvis-caldav-sync", daemon=True)
            self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        proc = self._process
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._process = None
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def info(self) -> dict:
        if not self.running:
            raise RuntimeError("The JARVIS CalDAV service is not running.")
        link = self.state.link.read()
        host, port = str(link.get("host") or ""), int(link.get("port") or 7443)
        if not host:
            raise RuntimeError("The public JARVIS cloud address is not configured.")
        base = f"https://{host}:{port}"
        token = self.setup_token
        return {
            "server_url": f"{base}{SCRIPT_NAME}/",
            "collection_url": f"{base}{SCRIPT_NAME}/{USERNAME}/{COLLECTION}/",
            "username": USERNAME, "list_name": COLLECTION,
            "setup_profile_url": f"{base}/caldav-setup/{token}.mobileconfig",
            "credentials_url": f"{base}/caldav-setup/{token}",
            "tls": "Install the JARVIS certificate profile and enable full trust on the iPhone before connecting.",
        }

    def handle_setup_request(self, handler) -> None:
        import html
        import plistlib
        import uuid
        from urllib.parse import urlsplit
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        path = urlsplit(handler.path).path
        prefix = "/caldav-setup/"
        supplied = path[len(prefix):] if path.startswith(prefix) else ""
        profile_requested = supplied.endswith(".mobileconfig")
        if profile_requested:
            supplied = supplied[:-len(".mobileconfig")]
        import hmac
        if not hmac.compare_digest(supplied, self.setup_token):
            handler.send_error(404)
            return
        link = self.state.link.read()
        host, port = str(link.get("host") or ""), int(link.get("port") or 7443)
        cert_path = self.state.dir / "link-cert.pem"
        if not host or not cert_path.is_file():
            handler.send_error(503, "JARVIS cloud certificate is not ready")
            return
        if profile_requested:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            root_payload = {
                "PayloadCertificateFileName": "JARVIS-Cloud-Root.cer",
                "PayloadContent": cert.public_bytes(Encoding.DER),
                "PayloadDescription": "Trust the private TLS certificate used by JARVIS Cloud",
                "PayloadDisplayName": "JARVIS Cloud Root Certificate",
                "PayloadIdentifier": "com.jarvis.caldav.root",
                "PayloadType": "com.apple.security.root",
                "PayloadUUID": str(uuid.uuid4()),
                "PayloadVersion": 1,
            }
            account_payload = {
                "CalDAVAccountDescription": "JARVIS",
                "CalDAVHostName": host,
                "CalDAVPort": port,
                "CalDAVPrincipalURL": f"https://{host}:{port}/dav/{USERNAME}/",
                "CalDAVUseSSL": True,
                "CalDAVUsername": USERNAME,
                "PayloadDisplayName": "JARVIS Reminders",
                "PayloadIdentifier": "com.jarvis.caldav.account",
                "PayloadType": "com.apple.caldav.account",
                "PayloadUUID": str(uuid.uuid4()),
                "PayloadVersion": 1,
            }
            profile = {
                "PayloadContent": [root_payload, account_payload],
                "PayloadDescription": "Install the JARVIS Reminders account and its TLS root certificate.",
                "PayloadDisplayName": "JARVIS Reminders",
                "PayloadIdentifier": "com.jarvis.caldav.profile",
                "PayloadOrganization": "JARVIS",
                "PayloadRemovalDisallowed": False,
                "PayloadType": "Configuration",
                "PayloadUUID": str(uuid.uuid4()),
                "PayloadVersion": 1,
            }
            data = plistlib.dumps(profile, fmt=plistlib.FMT_XML, sort_keys=False)
            handler.send_response(200)
            handler.send_header("Content-Type", "application/x-apple-aspen-config")
            handler.send_header("Content-Disposition", 'attachment; filename="JARVIS-Reminders.mobileconfig"')
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return

        setup = self.info()
        page = (
            "<!doctype html><html lang='pt-BR'><meta name='viewport' content='width=device-width'>"
            "<title>JARVIS - Lembretes</title><body style='font:16px system-ui;max-width:680px;"
            "margin:40px auto;padding:0 18px'><h1>JARVIS - Lembretes</h1>"
            "<p>1. Instale o perfil de configuracao do JARVIS no iPhone.</p>"
            "<p>2. Em Ajustes &gt; Geral &gt; Sobre &gt; Ajustes de Confianca de Certificados, "
            "ative a confianca total para o certificado raiz do JARVIS.</p>"
            "<p>3. Em Ajustes &gt; Apps &gt; Lembretes &gt; Contas de Lembretes, abra JARVIS e ative Lembretes para essa conta.</p>"
            "<p>4. Quando o iPhone solicitar a senha da conta, use os dados abaixo.</p>"
            "<h2>Conta CalDAV</h2><p>Servidor: " + html.escape(setup["server_url"]) +
            "</p><p>Usuario: <code>" + html.escape(USERNAME) +
            "</code></p><p>Senha: <code>" + html.escape(self._password) +
            "</code></p><p>Lista: JARVIS</p><p>Guarde essa senha como privada. "
            "Nao a compartilhe com outras pessoas.</p></body></html>"
        ).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(page)))
        handler.end_headers()
        handler.wfile.write(page)

    def _list_items(self) -> list[dict]:
        xml = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:resourcetype/></d:prop></d:propfind>'
        res = self._dav("PROPFIND", f"/{USERNAME}/{COLLECTION}/", xml,
                        {"Depth": "1", "Content-Type": "application/xml"})
        if res.status_code != 207:
            raise RuntimeError(f"CalDAV list failed ({res.status_code}).")
        root = ET.fromstring(res.content)
        output = []
        for node in root.findall(f"{{{DAV_NS}}}response"):
            href = node.findtext(f"{{{DAV_NS}}}href") or ""
            if not href or href.rstrip("/").endswith("/" + COLLECTION):
                continue
            if not href.lower().endswith(".ics"):
                continue
            etag = ""
            for propstat in node.findall(f"{{{DAV_NS}}}propstat"):
                prop = propstat.find(f"{{{DAV_NS}}}prop")
                if prop is not None:
                    etag = prop.findtext(f"{{{DAV_NS}}}getetag") or etag
            dav_path = unquote(urlsplit(href).path)
            if dav_path.startswith(SCRIPT_NAME):
                dav_path = dav_path[len(SCRIPT_NAME):] or "/"
            fetched = self._dav("GET", dav_path, timeout=15)
            if fetched.status_code != 200 or len(fetched.content) > MAX_ITEM_BYTES:
                continue
            parsed = parse_vtodo(fetched.text)
            if parsed:
                output.append({"href": href, "path": dav_path, "etag": etag,
                               "ics": fetched.text, "item": parsed})
        return output

    def _put_item(self, uid: str, item: dict, href: str = "", etag: str = ""):
        filename = hashlib.sha256(uid.encode("utf-8")).hexdigest() + ".ics"
        path = f"/{USERNAME}/{COLLECTION}/{filename}"
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if etag:
            headers["If-Match"] = etag
        result = self._dav("PUT", path, serialize_vtodo(item), headers)
        if result.status_code not in (200, 201, 204):
            return False, "", ""
        return True, f"{SCRIPT_NAME}{path}", result.headers.get("ETag", "")

    @staticmethod
    def _remote_id(uid: str) -> str:
        return "ios_" + hashlib.sha256(uid.encode("utf-8")).hexdigest()[:24]

    def _apply_remote(self, routine: dict | None, item: dict, href: str, etag: str) -> dict | None:
        due_ts = item.get("due_ts")
        if not due_ts:
            if routine is None:
                return None
            options = dict(routine.get("options") or {})
            meta = dict(options.get("jarvis_reminder") or {})
            meta.update({
                "status": item.get("status") or "open", "due_ts": 0.0,
                "message": item["message"], "caldav_uid": item["uid"],
                "caldav_href": href, "caldav_etag": etag,
                "caldav_remote_hash": _payload_hash(_remote_payload(item)),
                "caldav_local_hash": _payload_hash(_remote_payload(item)),
                "caldav_synced_once": True, "caldav_date_only": bool(item.get("date_only")),
                "caldav_last_sync": time.time(),
            })
            try:
                return self.runtime.routines.update(
                    routine["id"], name=item["message"][:80], text=item["message"],
                    enabled=False, options={"jarvis_reminder": meta},
                )
            except Exception:
                return routine
        now = time.time()
        status = item["status"]
        enabled = status == "open" and float(due_ts) > now
        uid, rid = item["uid"], self._remote_id(item["uid"])
        if routine is None:
            try:
                return self.runtime.routines.add(
                    name=item["message"][:80], kind="say", text=item["message"],
                    trigger={"type": "time", "rule": {"type": "once", "at_ts": float(due_ts)}},
                    source="cloud", next_ts=float(due_ts), enabled=enabled,
                    options={"jarvis_reminder": {
                        "id": rid, "status": status, "due_ts": float(due_ts),
                        "message": item["message"], "caldav_uid": uid,
                        "caldav_href": href, "caldav_etag": etag,
                        "caldav_remote_hash": _payload_hash(_remote_payload(item)),
                        "caldav_local_hash": _payload_hash(_remote_payload(item)),
                        "caldav_synced_once": True, "caldav_last_sync": time.time(),
                    }},
                )
            except Exception:
                return None
        options = dict(routine.get("options") or {})
        meta = dict(options.get("jarvis_reminder") or {})
        payload_hash = _payload_hash(_remote_payload(item))
        meta.update({
            "id": str(meta.get("id") or rid), "status": status,
            "due_ts": float(due_ts), "message": item["message"],
            "caldav_uid": uid, "caldav_href": href, "caldav_etag": etag,
            "caldav_remote_hash": payload_hash, "caldav_local_hash": payload_hash,
            "caldav_synced_once": True, "caldav_last_sync": time.time(),
        })
        if status == "open" and not enabled:
            meta["overdue"] = True
        else:
            meta.pop("overdue", None)
        try:
            return self.runtime.routines.update(
                routine["id"], name=item["message"][:80], text=item["message"],
                trigger={"type": "time", "rule": {"type": "once", "at_ts": float(due_ts)}},
                enabled=enabled, options={"jarvis_reminder": meta},
            )
        except Exception:
            return None

    def sync_once(self) -> dict:
        """Pull iPhone edits, then publish JARVIS edits. Simultaneous edits favor the phone."""
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "reason": "sync already running"}
        try:
            remote_rows = self._list_items()
            remote_by_uid = {row["item"]["uid"]: row for row in remote_rows}
            seen_uids = set()
            routines = [r for r in self.runtime.routines.list()
                        if r.get("source") == "cloud" and r.get("kind") == "say"
                        and isinstance((r.get("options") or {}).get("jarvis_reminder"), dict)]
            by_uid = {}
            for r in routines:
                meta = (r.get("options") or {}).get("jarvis_reminder") or {}
                uid = str(meta.get("caldav_uid") or "")
                if uid:
                    by_uid[uid] = r
            counts = {"imported": 0, "updated_from_iphone": 0, "published": 0, "cancelled": 0}

            for row in remote_rows:
                item, uid = row["item"], row["item"]["uid"]
                seen_uids.add(uid)
                routine = by_uid.get(uid)
                if not item.get("due_ts"):
                    if routine is not None:
                        updated = self._apply_remote(routine, item, row["href"], row["etag"])
                        if updated:
                            by_uid[uid] = updated
                            counts["updated_from_iphone"] += 1
                    continue
                remote_hash = _payload_hash(_remote_payload(item))
                if routine is None:
                    routine = self._apply_remote(None, item, row["href"], row["etag"])
                    if routine:
                        by_uid[uid] = routine
                        counts["imported"] += 1
                    continue

                meta = dict(((routine.get("options") or {}).get("jarvis_reminder") or {}))
                local_hash = _payload_hash(_local_payload(routine, meta))
                old_remote_hash = str(meta.get("caldav_remote_hash") or "")
                old_local_hash = str(meta.get("caldav_local_hash") or "")
                remote_changed = bool(old_remote_hash and remote_hash != old_remote_hash)
                local_changed = bool(old_local_hash and local_hash != old_local_hash)
                if not old_remote_hash:
                    remote_changed, local_changed = True, False
                if remote_changed:
                    updated = self._apply_remote(routine, item, row["href"], row["etag"])
                    if updated:
                        by_uid[uid] = updated
                        counts["updated_from_iphone"] += 1
                else:
                    meta["caldav_href"], meta["caldav_etag"] = row["href"], row["etag"]
                    meta["caldav_remote_hash"] = remote_hash
                    if local_changed:
                        payload = _local_payload(routine, meta)
                        payload["uid"] = uid
                        ok, href, etag = self._put_item(uid, payload, row["href"], row["etag"])
                        if ok:
                            meta.update({"caldav_href": href, "caldav_etag": etag,
                                         "caldav_remote_hash": _payload_hash(payload),
                                         "caldav_local_hash": _payload_hash(payload),
                                         "caldav_last_sync": time.time()})
                            counts["published"] += 1
                    else:
                        meta["caldav_local_hash"] = local_hash
                    options = dict(routine.get("options") or {})
                    options["jarvis_reminder"] = meta
                    try:
                        self.runtime.routines.update(routine["id"], options=options)
                    except Exception:
                        pass

            for uid, routine in by_uid.items():
                meta = dict(((routine.get("options") or {}).get("jarvis_reminder") or {}))
                if (meta.get("caldav_href") and uid not in seen_uids
                        and meta.get("caldav_synced_once")
                        and meta.get("status") not in {"done", "cancelled", "missed"}):
                    meta.update({"status": "cancelled", "caldav_deleted_by_user": True,
                                 "cancelled_at": time.time(), "caldav_last_sync": time.time()})
                    try:
                        self.runtime.routines.update(routine["id"], enabled=False,
                            options={"jarvis_reminder": meta})
                        counts["cancelled"] += 1
                    except Exception:
                        pass

            for routine in self.runtime.routines.list():
                if routine.get("source") != "cloud" or routine.get("kind") != "say":
                    continue
                options = dict(routine.get("options") or {})
                meta = dict(options.get("jarvis_reminder") or {})
                if not meta or meta.get("caldav_deleted_by_user"):
                    continue
                payload = _local_payload(routine, meta)
                if not payload["due_ts"] or not payload["message"]:
                    continue
                uid = str(meta.get("caldav_uid") or f"jarvis-{meta.get('id') or routine['id']}@jarvis")
                payload["uid"] = uid
                local_hash = _payload_hash(_remote_payload(payload))
                remote_hash = str(meta.get("caldav_remote_hash") or "")
                local_hash_at_sync = str(meta.get("caldav_local_hash") or "")
                if not meta.get("caldav_uid") or (local_hash != local_hash_at_sync and local_hash != remote_hash):
                    ok, href, etag = self._put_item(uid, payload, str(meta.get("caldav_href") or ""),
                                                   str(meta.get("caldav_etag") or ""))
                    if not ok:
                        continue
                    meta.update({"caldav_uid": uid, "caldav_href": href, "caldav_etag": etag,
                                 "caldav_remote_hash": local_hash, "caldav_local_hash": local_hash,
                                 "caldav_synced_once": True, "caldav_last_sync": time.time()})
                    options["jarvis_reminder"] = meta
                    try:
                        self.runtime.routines.update(routine["id"], options=options)
                    except Exception:
                        pass
                    counts["published"] += 1
                elif meta.get("caldav_uid"):
                    meta["caldav_synced_once"] = True
                    options["jarvis_reminder"] = meta
                    try:
                        self.runtime.routines.update(routine["id"], options=options)
                    except Exception:
                        pass

            return {"ok": True, **counts}
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:180]}"}
        finally:
            self._lock.release()

    def _sync_loop(self) -> None:
        while not self._stop.is_set():
            result = self.sync_once()
            if result.get("ok") is False:
                try:
                    self.runtime.log(f"SYS: CalDAV sync ? {result.get('reason', 'unavailable')}")
                except Exception:
                    pass
            self._stop.wait(SYNC_SECONDS)

