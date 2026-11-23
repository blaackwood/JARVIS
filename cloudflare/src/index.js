const DAV_ROOT = "/dav";
const PRINCIPAL = "/dav/principals/jarvis/";
const HOME = "/dav/calendars/jarvis/";
const DEFAULT_CALENDAR_ID = "Lembretes";
const CALENDAR = HOME + DEFAULT_CALENDAR_ID + "/";
const MAX_ICS_BYTES = 256_000;

const XML_HEAD = '<?xml version="1.0" encoding="utf-8"?>';
const NS = 'xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:cs="http://calendarserver.org/ns/" xmlns:i="http://apple.com/ns/ical/"';

function xmlEscape(value = "") {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"
  })[ch]);
}
function xmlResponse(status, body, headers = {}) {
  return new Response(body, {
    status,
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "no-store",
      "DAV": "1, 2, calendar-access",
      "MS-Author-Via": "DAV",
      ...headers
    }
  });
}
function jsonResponse(status, body, headers = {}) {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store", ...headers }
  });
}
function constantTimeEqual(a, b) {
  const left = String(a || "");
  const right = String(b || "");
  let diff = left.length ^ right.length;
  const size = Math.max(left.length, right.length);
  for (let i = 0; i < size; i += 1) {
    diff |= (left.charCodeAt(i) || 0) ^ (right.charCodeAt(i) || 0);
  }
  return diff === 0;
}
function bearerOk(request, env) {
  const expected = String(env.JARVIS_ADMIN_TOKEN || "");
  const supplied = String(request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  return expected.length >= 32 && constantTimeEqual(supplied, expected);
}
function basicOk(request, env) {
  const expectedUser = String(env.CALDAV_USERNAME || "jarvis");
  const expectedPass = String(env.CALDAV_PASSWORD || "");
  const header = request.headers.get("Authorization") || "";
  if (!header.startsWith("Basic ") || expectedPass.length < 24) return false;
  try {
    const decoded = atob(header.slice(6));
    const split = decoded.indexOf(":");
    if (split < 0) return false;
    return constantTimeEqual(decoded.slice(0, split), expectedUser) &&
      constantTimeEqual(decoded.slice(split + 1), expectedPass);
  } catch {
    return false;
  }
}
function unauthorized() {
  return new Response("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="JARVIS Reminders", charset="UTF-8"',
      "Cache-Control": "no-store"
    }
  });
}
function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}
function validId(raw) {
  const id = String(raw || "");
  return /^[A-Za-z0-9_.@-]{1,180}$/.test(id) ? id : "";
}
function calendarIdFromPath(pathname) {
  const match = String(pathname || "").match(/^\/dav\/calendars\/jarvis\/([^/]+)\/?$/);
  if (!match) return "";
  try { return validId(decodeURIComponent(match[1])); } catch { return ""; }
}
function resourceInfo(pathname) {
  const match = String(pathname || "").match(/^\/dav\/calendars\/jarvis\/([^/]+)\/([^/]+)\.ics\/?$/);
  if (!match) return null;
  try {
    const calendarId = validId(decodeURIComponent(match[1]));
    const id = validId(decodeURIComponent(match[2]));
    return calendarId && id ? { calendarId, id } : null;
  } catch { return null; }
}
function resourceId(pathname) {
  return resourceInfo(pathname)?.id || "";
}
async function sha256(value) {
  const bytes = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((v) => v.toString(16).padStart(2, "0")).join("");
}
async function getReminder(db, id) {
  return db.prepare("SELECT * FROM reminders WHERE id = ?").bind(id).first();
}
async function listReminders(db, includeCancelled = false, calendarId = "") {
  const statusClause = includeCancelled ? "" : " WHERE status != 'cancelled'";
  const filterClause = calendarId
    ? (statusClause ? " AND calendar_id = ?" : " WHERE calendar_id = ?")
    : "";
  const sql = "SELECT * FROM reminders" + statusClause + filterClause +
    " ORDER BY COALESCE(due_ts, 0), created_at";
  const statement = db.prepare(sql);
  const result = await (calendarId ? statement.bind(calendarId) : statement).all();
  return result.results || [];
}
async function listCalendars(db) {
  const result = await db.prepare(
    "SELECT calendar_id, display_name FROM calendars ORDER BY created_at, calendar_id"
  ).all();
  return result.results || [];
}
async function getCalendar(db, calendarId) {
  return db.prepare("SELECT calendar_id, display_name FROM calendars WHERE calendar_id = ?")
    .bind(calendarId).first();
}
async function createCalendar(db, calendarId, displayName) {
  await db.prepare(
    "INSERT OR IGNORE INTO calendars (calendar_id, display_name, created_at) VALUES (?,?,?)"
  ).bind(calendarId, String(displayName || calendarId).slice(0, 100), nowSeconds()).run();
  return await getCalendar(db, calendarId);
}
async function bumpSyncSequence(db) {
  await db.prepare("UPDATE dav_meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'sync_seq'").run();
  const row = await db.prepare("SELECT value FROM dav_meta WHERE key = 'sync_seq'").first();
  return Number(row?.value || 1);
}
async function currentSyncSequence(db) {
  const row = await db.prepare("SELECT value FROM dav_meta WHERE key = 'sync_seq'").first();
  return Number(row?.value || 1);
}
async function saveReminder(db, item, rawIcs = "") {
  const previous = await getReminder(db, item.id);
  const calendarId = validId(item.calendar_id || previous?.calendar_id || DEFAULT_CALENDAR_ID) || DEFAULT_CALENDAR_ID;
  const now = nowSeconds();
  const created = Number(previous?.created_at || item.created_at || now);
  const seq = await bumpSyncSequence(db);
  const etag = await sha256(rawIcs || JSON.stringify({
    id: item.id, message: item.message, due_ts: item.due_ts,
    due_raw: item.due_raw, status: item.status,
    description: item.description, sequence: seq
  }));
  await db.prepare(
    "INSERT INTO reminders (calendar_id,id,message,due_ts,due_raw,date_only,status,description,created_at,updated_at,completed_at,cancelled_at,etag,sequence) " +
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) " +
    "ON CONFLICT(id) DO UPDATE SET calendar_id=excluded.calendar_id,message=excluded.message,due_ts=excluded.due_ts,due_raw=excluded.due_raw," +
    "date_only=excluded.date_only,status=excluded.status,description=excluded.description," +
    "updated_at=excluded.updated_at,completed_at=excluded.completed_at,cancelled_at=excluded.cancelled_at," +
    "etag=excluded.etag,sequence=excluded.sequence"
  ).bind(
    calendarId, item.id, String(item.message || "JARVIS reminder").slice(0, 200),
    item.due_ts == null ? null : Number(item.due_ts),
    item.due_raw || null, item.date_only ? 1 : 0,
    ["open", "done", "cancelled", "missed"].includes(item.status) ? item.status : "open",
    String(item.description || "").slice(0, 2000),
    created, now, item.completed_at || null, item.cancelled_at || null, etag, seq
  ).run();
  await db.prepare(
    "INSERT INTO dav_changes (sequence, reminder_id, status, changed_at) VALUES (?,?,?,?)"
  ).bind(seq, item.id, item.status, now).run();
  return await getReminder(db, item.id);
}
async function listChangesSince(db, sequence) {
  const result = await db.prepare(
    "SELECT sequence, reminder_id, status, changed_at FROM dav_changes WHERE sequence > ? ORDER BY sequence ASC LIMIT 500"
  ).bind(Number(sequence || 0)).all();
  return result.results || [];
}
function apiReminder(row) {
  return {
    id: row.id,
    cloud_id: row.id,
    message: row.message,
    due_ts: row.due_ts == null ? null : Number(row.due_ts),
    status: row.status,
    description: row.description || "",
    completed_at: row.completed_at || null,
    cancelled_at: row.cancelled_at || null,
    updated_at: row.updated_at || null,
    date_only: !!row.date_only
  };
}
function escapeIcal(value) {
  return String(value || "").replace(/\\/g, "\\\\").replace(/\r\n|\r|\n/g, "\\n")
    .replace(/;/g, "\\;").replace(/,/g, "\\,");
}
function unescapeIcal(value) {
  return String(value || "").replace(/\\[nN]/g, "\n").replace(/\\([\\;,])/g, "$1");
}
function formatUtc(seconds) {
  return new Date(Number(seconds) * 1000).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}
function serializeTodo(item) {
  const stamp = formatUtc(item.updated_at || nowSeconds());
  const status = item.status === "done" || item.status === "missed" ? "COMPLETED" :
    item.status === "cancelled" ? "CANCELLED" : "NEEDS-ACTION";
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0",
    "PRODID:-//JARVIS//Apple Reminders//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VTODO", "UID:" + escapeIcal(item.id), "DTSTAMP:" + stamp,
    "LAST-MODIFIED:" + stamp, "SUMMARY:" + escapeIcal(item.message || "JARVIS reminder")
  ];
  if (item.date_only && item.due_raw) lines.push("DUE;VALUE=DATE:" + item.due_raw);
  else if (item.due_ts != null) lines.push("DUE:" + formatUtc(item.due_ts));
  if (item.description) lines.push("DESCRIPTION:" + escapeIcal(item.description));
  lines.push("STATUS:" + status);
  if (status === "COMPLETED") lines.push("COMPLETED:" + stamp);
  lines.push("END:VTODO", "END:VCALENDAR");
  return lines.join("\r\n") + "\r\n";
}
function parsePropertyLine(line) {
  const index = line.indexOf(":");
  if (index < 0) return null;
  const left = line.slice(0, index).split(";");
  const params = {};
  for (const part of left.slice(1)) {
    const equals = part.indexOf("=");
    if (equals > 0) params[part.slice(0, equals).toUpperCase()] = part.slice(equals + 1).replace(/^"|"$/g, "");
  }
  return { name: left[0].toUpperCase(), params, value: line.slice(index + 1) };
}
function localDateToEpoch(value, zone) {
  const match = String(value).match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/);
  if (!match) return null;
  const [, y, mo, d, h, mi, s] = match.map(Number);
  const target = Date.UTC(y, mo - 1, d, h, mi, s);
  if (!zone) return target / 1000;
  try {
    let guess = target;
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
    });
    for (let i = 0; i < 4; i += 1) {
      const parts = Object.fromEntries(fmt.formatToParts(new Date(guess)).map((p) => [p.type, p.value]));
      const represented = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day),
        Number(parts.hour), Number(parts.minute), Number(parts.second));
      const delta = target - represented;
      guess += delta;
      if (delta === 0) break;
    }
    return Math.floor(guess / 1000);
  } catch {
    return target / 1000;
  }
}
function parseDue(property, defaultZone) {
  if (!property) return { due_ts: null, due_raw: null, date_only: false };
  const raw = String(property.value || "").trim();
  if (property.params.VALUE?.toUpperCase() === "DATE" || /^\d{8}$/.test(raw)) {
    if (!/^\d{8}$/.test(raw)) return { due_ts: null, due_raw: null, date_only: false };
    return { due_ts: null, due_raw: raw, date_only: true };
  }
  const compact = raw.replace(/[-:]/g, "");
  const match = compact.match(/^(\d{8}T\d{6})(Z)?$/);
  if (!match) return { due_ts: null, due_raw: null, date_only: false };
  const value = match[1];
  const due = match[2] === "Z" ? Date.UTC(
    Number(value.slice(0, 4)), Number(value.slice(4, 6)) - 1, Number(value.slice(6, 8)),
    Number(value.slice(9, 11)), Number(value.slice(11, 13)), Number(value.slice(13, 15))
  ) / 1000 : localDateToEpoch(value, property.params.TZID || defaultZone);
  return { due_ts: due, due_raw: raw, date_only: false };
}
function parseTodo(ics, pathId, defaultZone) {
  if (new TextEncoder().encode(ics).length > MAX_ICS_BYTES) throw new Error("Calendar item is too large.");
  const physical = String(ics).replace(/\r\n[ \t]/g, "").replace(/\n[ \t]/g, "").split(/\r?\n/);
  const props = new Map();
  let inTodo = false;
  for (const line of physical) {
    if (line.toUpperCase() === "BEGIN:VTODO") { inTodo = true; continue; }
    if (line.toUpperCase() === "END:VTODO") break;
    if (!inTodo) continue;
    const prop = parsePropertyLine(line);
    if (prop) props.set(prop.name, prop);
  }
  const summary = unescapeIcal(props.get("SUMMARY")?.value || "").trim();
  if (!summary) throw new Error("A JARVIS reminder needs a SUMMARY.");
  const due = parseDue(props.get("DUE") || props.get("DTSTART"), defaultZone);
  const rawStatus = String(props.get("STATUS")?.value || "NEEDS-ACTION").toUpperCase();
  const status = rawStatus === "COMPLETED" ? "done" : rawStatus === "CANCELLED" ? "cancelled" : "open";
  const completedProp = props.get("COMPLETED");
  let completedAt = null;
  if (completedProp) {
    const parsed = parseDue({ value: completedProp.value, params: completedProp.params }, defaultZone);
    if (parsed.due_ts) completedAt = parsed.due_ts;
  }
  return {
    id: pathId,
    message: summary.slice(0, 200),
    due_ts: due.due_ts,
    due_raw: due.due_raw,
    date_only: due.date_only,
    status,
    description: unescapeIcal(props.get("DESCRIPTION")?.value || "").slice(0, 2000),
    completed_at: completedAt,
    cancelled_at: status === "cancelled" ? nowSeconds() : null
  };
}
function itemHref(id, calendarId = DEFAULT_CALENDAR_ID) {
  return HOME + encodeURIComponent(calendarId) + "/" + encodeURIComponent(id) + ".ics";
}
function propstat(props) {
  return "<d:propstat><d:prop>" + props + "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>";
}
function responseNode(href, props, extra = "") {
  return "<d:response><d:href>" + xmlEscape(href) + "</d:href>" +
    propstat(props) + extra + "</d:response>";
}
function discoveryRootProps() {
  return '<d:resourcetype><d:collection/></d:resourcetype>' +
    '<d:displayname>JARVIS</d:displayname>' +
    '<d:current-user-principal><d:href>' + PRINCIPAL + '</d:href></d:current-user-principal>' +
    '<d:principal-URL><d:href>' + PRINCIPAL + '</d:href></d:principal-URL>' +
    '<d:principal-collection-set><d:href>/dav/principals/</d:href></d:principal-collection-set>';
}
function isPrincipalDiscoveryPath(pathname) {
  return pathname === PRINCIPAL.slice(0, -1) || pathname === PRINCIPAL ||
    pathname === "/principals" || pathname === "/principals/" ||
    pathname === "/calendar/dav/jarvis/user" || pathname === "/calendar/dav/jarvis/user/";
}
function principalProps(origin = "") {
  // Return fully-qualified same-origin hrefs for Apple Reminders discovery.
  const base = String(origin || "").replace(/\/$/, "");
  const absolute = (path) => base + path;
  const principalHref = absolute(PRINCIPAL);
  const homeHref = absolute(HOME);
  return '<d:resourcetype><d:principal/></d:resourcetype>' +
    "<d:displayname>JARVIS</d:displayname>" +
    "<d:current-user-principal><d:href>" + xmlEscape(principalHref) + "</d:href></d:current-user-principal>" +
    "<d:principal-URL><d:href>" + xmlEscape(principalHref) + "</d:href></d:principal-URL>" +
    "<d:principal-collection-set><d:href>" + xmlEscape(absolute("/dav/principals/")) + "</d:href></d:principal-collection-set>" +
    '<d:resource-id><d:href>urn:uuid:6f9c4b53-3f74-4e9e-a2c6-d7b7c4c942d3</d:href></d:resource-id>' +
    "<c:calendar-home-set><d:href>" + xmlEscape(homeHref) + "</d:href></c:calendar-home-set>" +
    "<c:calendar-user-address-set><d:href>" + xmlEscape(principalHref) + "</d:href></c:calendar-user-address-set>" +
    "<c:calendar-user-type>INDIVIDUAL</c:calendar-user-type>" +
    "<d:supported-report-set>" +
    '<d:supported-report><d:report><c:calendar-query/></d:report></d:supported-report>' +
    '<d:supported-report><d:report><c:calendar-multiget/></d:report></d:supported-report>' +
    '<d:supported-report><d:report><d:sync-collection/></d:report></d:supported-report>' +
    "</d:supported-report>";
}
function principalMissingPropstat(body) {
  const propBlock = String(body || "").match(/<(?:[A-Za-z0-9_-]+:)?prop(?:\s[^>]*)?>([\s\S]*?)<\/(?:[A-Za-z0-9_-]+:)?prop>/i);
  if (!propBlock) return "";
  const namespaces = {};
  for (const match of String(body).matchAll(/xmlns(?::([A-Za-z0-9_-]+))?\s*=\s*["']([^"']+)["']/g)) {
    namespaces[match[1] || ""] = match[2];
  }
  const supported = new Set([
    "DAV:|resourcetype", "DAV:|displayname", "DAV:|current-user-principal",
    "DAV:|principal-URL", "DAV:|principal-collection-set", "DAV:|resource-id",
    "DAV:|supported-report-set",
    "urn:ietf:params:xml:ns:caldav|calendar-home-set",
    "urn:ietf:params:xml:ns:caldav|calendar-user-address-set",
    "urn:ietf:params:xml:ns:caldav|calendar-user-type"
  ]);
  const missing = [];
  const seen = new Set();
  for (const match of propBlock[1].matchAll(/<(?:([A-Za-z0-9_-]+):)?([A-Za-z][A-Za-z0-9_-]*)\b[^>]*\/>/g)) {
    const prefix = match[1] || "";
    const local = match[2];
    const namespace = namespaces[prefix] || "";
    const key = namespace + "|" + local;
    if (supported.has(key) || seen.has(key)) continue;
    seen.add(key);
    if (namespace === "DAV:") missing.push("<d:" + local + "/>");
    else if (namespace === "urn:ietf:params:xml:ns:caldav") missing.push("<c:" + local + "/>");
    else if (namespace) missing.push('<x:' + local + ' xmlns:x="' + xmlEscape(namespace) + '"/>');
    else missing.push("<d:" + local + "/>");
  }
  return missing.length
    ? '<d:propstat><d:prop>' + missing.join("") +
      "</d:prop><d:status>HTTP/1.1 404 Not Found</d:status></d:propstat>"
    : "";
}
function homeProps() {
  return '<d:resourcetype><d:collection/></d:resourcetype><d:displayname>Calendars</d:displayname>';
}
function calendarProps(seq, displayName = "JARVIS") {
  const name = xmlEscape(displayName || "JARVIS");
  return '<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>' +
    "<d:displayname>" + name + "</d:displayname>" +
    "<c:calendar-description>" + name + " Reminders</c:calendar-description>" +
    "<c:supported-calendar-component-set><c:comp name=\"VTODO\"/></c:supported-calendar-component-set>" +
    "<c:supported-calendar-data><c:calendar-data content-type=\"text/calendar\" version=\"2.0\"/></c:supported-calendar-data>" +
    "<d:owner><d:href>" + PRINCIPAL + "</d:href></d:owner>" +
    "<d:current-user-privilege-set><d:privilege><d:all/></d:privilege></d:current-user-privilege-set>" +
    "<cs:getctag>" + seq + "</cs:getctag>" +
    "<d:sync-token>urn:jarvis:sync:" + seq + "</d:sync-token>" +
    "<c:calendar-timezone>BEGIN:VTIMEZONE\r\nTZID:UTC\r\nEND:VTIMEZONE</c:calendar-timezone>";
}
function resourceProps(row, includeData = false) {
  let props = '<d:resourcetype/><d:getcontenttype>text/calendar; charset=utf-8</d:getcontenttype>' +
    "<d:getcontentlength>" + new TextEncoder().encode(serializeTodo(row)).length + "</d:getcontentlength>" +
    "<d:getetag>&quot;" + xmlEscape(row.etag) + "&quot;</d:getetag>" +
    "<d:getlastmodified>" + new Date(Number(row.updated_at) * 1000).toUTCString() + "</d:getlastmodified>";
  if (includeData) props += "<c:calendar-data>" + xmlEscape(serializeTodo(row)) + "</c:calendar-data>";
  return props;
}
function multistatus(nodes, seq = null) {
  return XML_HEAD + '<d:multistatus ' + NS + ">" +
    nodes.join("") + (seq == null ? "" : "<d:sync-token>urn:jarvis:sync:" + seq + "</d:sync-token>") +
    "</d:multistatus>";
}
function extractHrefs(body) {
  const out = [];
  const regex = /<(?:[A-Za-z0-9_-]+:)?href\b[^>]*>([\s\S]*?)<\/(?:[A-Za-z0-9_-]+:)?href>/gi;
  let match;
  while ((match = regex.exec(body))) {
    out.push(match[1].replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">"));
  }
  return out;
}
async function handlePropfind(request, env, pathname) {
  const db = env.DB;
  const depth = request.headers.get("Depth") || "0";
  const discoveryBody = await request.clone().text();
  console.log("DAV_PROPFIND", JSON.stringify({
    pathname, depth, userAgent: request.headers.get("User-Agent") || "",
    requestedProperties: [...discoveryBody.matchAll(/<(?:[A-Za-z0-9_-]+:)?([A-Za-z][A-Za-z0-9_-]*)\b/g)].map((m) => m[1]).slice(0, 60)
  }));
  const seq = await currentSyncSequence(db);
  const nodes = [];
  if (pathname === "/" || pathname === "/dav" || pathname === "/dav/") {
    const rootHref = pathname === "/" ? "/" : "/dav/";
    nodes.push(responseNode(rootHref, discoveryRootProps()));
  } else if (isPrincipalDiscoveryPath(pathname)) {
    // Compatibility aliases used by Apple's CalDAV discovery probes.
    nodes.push(responseNode(
      new URL(pathname, new URL(request.url).origin).href,
      principalProps(new URL(request.url).origin),
      principalMissingPropstat(discoveryBody)
    ));
  } else if (pathname === HOME.slice(0, -1) || pathname === HOME) {
    nodes.push(responseNode(HOME, homeProps()));
    if (depth !== "0") {
      const calendars = await listCalendars(db);
      for (const calendar of calendars) {
        const calendarPath = HOME + encodeURIComponent(calendar.calendar_id) + "/";
        nodes.push(responseNode(calendarPath, calendarProps(seq, calendar.display_name)));
      }
    }
  } else if (calendarIdFromPath(pathname)) {
    const calendarId = calendarIdFromPath(pathname);
    const calendar = await getCalendar(db, calendarId);
    if (!calendar) return new Response("Calendar not found", { status: 404 });
    const calendarPath = HOME + encodeURIComponent(calendarId) + "/";
    nodes.push(responseNode(calendarPath, calendarProps(seq, calendar.display_name)));
    if (depth !== "0") {
      const rows = await listReminders(db, false, calendarId);
      for (const row of rows) nodes.push(responseNode(itemHref(row.id, calendarId), resourceProps(row, false)));
    }
  } else {
    const info = resourceInfo(pathname);
    if (!info) return new Response("Not found", { status: 404 });
    const row = await getReminder(db, info.id);
    if (!row || row.status === "cancelled" || row.calendar_id !== info.calendarId) {
      return new Response("Not found", { status: 404 });
    }
    nodes.push(responseNode(itemHref(row.id, info.calendarId), resourceProps(row, false)));
  }
  const responseBody = multistatus(nodes, calendarIdFromPath(pathname) ? seq : null);
  if (pathname === PRINCIPAL || pathname === PRINCIPAL.slice(0, -1)) {
    console.log("DAV_PRINCIPAL_RESPONSE", JSON.stringify({ status: 207, body: responseBody }));
  }
  return xmlResponse(207, responseBody);
}
async function handleReport(request, env, pathname) {
  const calendarId = calendarIdFromPath(pathname);
  if (!calendarId || !(await getCalendar(env.DB, calendarId))) {
    return xmlResponse(207, multistatus([]));
  }
  const body = await request.text();
  const seq = await currentSyncSequence(env.DB);

  if (/sync-collection/i.test(body)) {
    const tokenMatch = body.match(/<(?:[A-Za-z0-9_-]+:)?sync-token\b[^>]*>([\s\S]*?)<\/(?:[A-Za-z0-9_-]+:)?sync-token>/i);
    const tokenText = tokenMatch ? tokenMatch[1].trim() : "";
    const parsedToken = Number((tokenText.match(/(\d+)$/) || [])[1] || 0);
    const changes = parsedToken > 0 && parsedToken <= seq
      ? await listChangesSince(env.DB, parsedToken)
      : [];
    let nodes = [];
    if (!parsedToken || parsedToken > seq) {
      const rows = await listReminders(env.DB, false, calendarId);
      nodes = rows.map((row) => responseNode(itemHref(row.id, calendarId), resourceProps(row, true)));
    } else {
      for (const change of changes) {
        if (change.status === "cancelled") {
          const removed = await getReminder(env.DB, change.reminder_id);
          if (removed?.calendar_id === calendarId) {
            nodes.push("<d:response><d:href>" + xmlEscape(itemHref(change.reminder_id, calendarId)) +
              "</d:href><d:status>HTTP/1.1 404 Not Found</d:status></d:response>");
          }
        } else {
          const row = await getReminder(env.DB, change.reminder_id);
          if (row && row.calendar_id === calendarId && row.status !== "cancelled") {
            nodes.push(responseNode(itemHref(row.id, calendarId), resourceProps(row, true)));
          }
        }
      }
    }
    return xmlResponse(207, multistatus(nodes, seq));
  }

  const hrefs = extractHrefs(body);
  const wanted = new Set(hrefs.map((href) => {
    const match = href.match(/\/([^/]+)\.ics\/?$/);
    if (!match) return "";
    try { return decodeURIComponent(match[1]); } catch { return ""; }
  }).filter(Boolean));
  let rows = await listReminders(env.DB, false, calendarId);
  if (/calendar-multiget/i.test(body) && wanted.size) rows = rows.filter((row) => wanted.has(row.id));
  const includeData = /calendar-data/i.test(body);
  const nodes = rows.map((row) => responseNode(itemHref(row.id, calendarId), resourceProps(row, includeData)));
  return xmlResponse(207, multistatus(nodes, seq));
}
async function handlePut(request, env, pathname) {
  const info = resourceInfo(pathname);
  if (!info || !(await getCalendar(env.DB, info.calendarId))) return new Response("Not found", { status: 404 });
  const { id, calendarId } = info;
  const raw = await request.text();
  if (new TextEncoder().encode(raw).length > MAX_ICS_BYTES) {
    return jsonResponse(413, { error: "Calendar item is too large." });
  }
  let item;
  try { item = parseTodo(raw, id, env.DEFAULT_TIMEZONE || "America/Sao_Paulo"); }
  catch (error) { return jsonResponse(400, { error: error.message || "Invalid VTODO." }); }
  item.calendar_id = calendarId;
  const existing = await getReminder(env.DB, id);
  if (existing && existing.calendar_id !== calendarId) return new Response("Resource belongs to another calendar", { status: 409 });
  const ifMatch = request.headers.get("If-Match");
  const ifNone = request.headers.get("If-None-Match");
  if (ifMatch && (!existing || ifMatch.replace(/"/g, "") !== existing.etag)) {
    return new Response("ETag mismatch", { status: 412 });
  }
  if (ifNone === "*" && existing) return new Response("Resource already exists", { status: 412 });
  const saved = await saveReminder(env.DB, item, raw);
  return new Response(null, {
    status: existing ? 204 : 201,
    headers: {
      "ETag": '"' + saved.etag + '"',
      "Location": itemHref(id, calendarId),
      "Cache-Control": "no-store",
      "DAV": "1, 2, calendar-access"
    }
  });
}
async function handleDelete(env, pathname) {
  const info = resourceInfo(pathname);
  if (!info) return new Response("Not found", { status: 404 });
  const { id, calendarId } = info;
  const existing = await getReminder(env.DB, id);
  if (!existing || existing.calendar_id !== calendarId || existing.status === "cancelled") {
    return new Response("Not found", { status: 404 });
  }
  await saveReminder(env.DB, {
    ...existing, status: "cancelled", cancelled_at: nowSeconds()
  });
  return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
}
function profileXml(host) {
  const payloadRoot = crypto.randomUUID();
  const payloadAccount = crypto.randomUUID();
  const payload = crypto.randomUUID();
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>PayloadContent</key><array><dict>
<key>CalDAVAccountDescription</key><string>JARVIS</string>
<key>CalDAVHostName</key><string>${xmlEscape(host)}</string>
<key>CalDAVPort</key><integer>443</integer>
<key>CalDAVUseSSL</key><true/>
<key>CalDAVUsername</key><string>${xmlEscape("jarvis")}</string>
<key>PayloadDisplayName</key><string>JARVIS Reminders</string>
<key>PayloadIdentifier</key><string>com.jarvis.caldav.account</string>
<key>PayloadType</key><string>com.apple.caldav.account</string>
<key>PayloadUUID</key><string>${payloadAccount}</string>
<key>PayloadVersion</key><integer>1</integer>
</dict></array>
<key>PayloadDescription</key><string>Connect Apple Reminders to JARVIS over encrypted HTTPS.</string>
<key>PayloadDisplayName</key><string>JARVIS Reminders</string>
<key>PayloadIdentifier</key><string>com.jarvis.caldav.profile</string>
<key>PayloadOrganization</key><string>JARVIS</string>
<key>PayloadRemovalDisallowed</key><false/>
<key>PayloadType</key><string>Configuration</string>
<key>PayloadUUID</key><string>${payload}</string>
<key>PayloadVersion</key><integer>1</integer>
</dict></plist>`;
}
function setupPage(origin, username, password) {
  return `<!doctype html><html lang="en"><meta name="viewport" content="width=device-width">
<meta name="referrer" content="no-referrer"><title>JARVIS Reminders credentials</title>
<body style="font:16px system-ui;max-width:680px;margin:40px auto;padding:0 20px;color:#222">
<h1>JARVIS Reminders</h1><p>This is your private CalDAV account setup page. Do not share this page or its URL.</p>
<p>Username: <code>${xmlEscape(username)}</code></p>
<p>Password: <code id="password">${xmlEscape(password)}</code></p>
<p>Server: <code>${xmlEscape(origin)}${DAV_ROOT}/</code></p>
<p>List: <code>${xmlEscape(origin + CALENDAR)}</code></p>
<p>Copy the password into the iOS CalDAV sign-in prompt. This page is not cached.</p>
</body></html>`;
}
async function handleApi(request, env, url) {
  if (!bearerOk(request, env)) return jsonResponse(401, { error: "Unauthorized" });
  if (url.pathname === "/api/health" && request.method === "GET") {
    if (!env.DB) return jsonResponse(503, { error: "D1 database binding is missing." });
    return jsonResponse(200, { ok: true, server: "jarvis-cloudflare", name: "JARVIS", storage: "D1" });
  }
  if (url.pathname === "/api/setup" && request.method === "GET") {
    const token = String(env.SETUP_TOKEN || "");
    if (token.length < 32 || !env.CALDAV_PASSWORD) {
      return jsonResponse(503, { error: "Private iPhone setup secrets are not configured." });
    }
    return jsonResponse(200, {
      ok: true,
      username: env.CALDAV_USERNAME || "jarvis",
      server_url: url.origin + DAV_ROOT + "/",
      collection_url: url.origin + CALENDAR,
      setup_profile_url: url.origin + "/setup/" + token + "/JARVIS.mobileconfig",
      credentials_url: url.origin + "/setup/" + token
    });
  }
  if (url.pathname === "/api/reminders" && request.method === "GET") {
    const rows = await listReminders(env.DB, true);
    return jsonResponse(200, { ok: true, reminders: rows.map(apiReminder) });
  }
  if (url.pathname === "/api/reminders" && request.method === "POST") {
    let body;
    try { body = await request.json(); } catch { return jsonResponse(400, { error: "Invalid JSON." }); }
    const action = String(body.action || "upsert").toLowerCase();
    const id = validId(body.id);
    if (!id) return jsonResponse(400, { error: "A valid reminder id is required." });
    if (action === "state") {
      const current = await getReminder(env.DB, id);
      if (!current) return jsonResponse(404, { error: "Reminder not found." });
      const status = String(body.status || "").toLowerCase();
      if (!["open", "done", "cancelled", "missed"].includes(status)) {
        return jsonResponse(400, { error: "Invalid reminder status." });
      }
      const saved = await saveReminder(env.DB, {
        ...current, status,
        completed_at: status === "done" ? nowSeconds() : null,
        cancelled_at: status === "cancelled" ? nowSeconds() : null
      });
      return jsonResponse(200, { ok: true, reminder: apiReminder(saved) });
    }
    if (action !== "upsert") return jsonResponse(400, { error: "Unsupported reminder action." });
    const message = String(body.message || "").trim().slice(0, 200);
    if (!message) return jsonResponse(400, { error: "A reminder message is required." });
    const due = body.due_ts == null ? null : Number(body.due_ts);
    if (due != null && (!Number.isFinite(due) || due <= 0)) return jsonResponse(400, { error: "Invalid due time." });
    const current = await getReminder(env.DB, id);
    const saved = await saveReminder(env.DB, {
      ...(current || {}), id, message, due_ts: due, due_raw: null, date_only: false,
      status: String(body.status || current?.status || "open"),
      description: String(body.description || "").slice(0, 2000),
      completed_at: body.status === "done" ? nowSeconds() : current?.completed_at || null,
      cancelled_at: body.status === "cancelled" ? nowSeconds() : current?.cancelled_at || null
    });
    return jsonResponse(200, { ok: true, reminder: apiReminder(saved) });
  }
  return jsonResponse(404, { error: "Not found." });
}
async function handleDav(request, env, url) {
  const pathname = url.pathname;
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 200,
      headers: {
        "Allow": "OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, REPORT, PROPPATCH, MKCOL, MKCALENDAR",
        "DAV": "1, 2, calendar-access",
        "MS-Author-Via": "DAV",
        "Cache-Control": "no-store"
      }
    });
  }
  if (!basicOk(request, env)) {
    if (!env.CALDAV_PASSWORD || String(env.CALDAV_PASSWORD).length < 24) {
      return new Response("CalDAV password is not configured.", { status: 503 });
    }
    return unauthorized();
  }
  if (request.method === "PROPFIND") return handlePropfind(request, env, pathname);
  if (request.method === "REPORT") return handleReport(request, env, pathname);
  if (request.method === "PUT") return handlePut(request, env, pathname);
  if (request.method === "DELETE") return handleDelete(env, pathname);
  if (request.method === "GET" || request.method === "HEAD") {
    const info = resourceInfo(pathname);
    if (!info) return new Response("Not found", { status: 404 });
    const row = await getReminder(env.DB, info.id);
    if (!row || row.calendar_id !== info.calendarId || row.status === "cancelled") {
      return new Response("Not found", { status: 404 });
    }
    const etag = '"' + row.etag + '"';
    if (request.headers.get("If-None-Match") === etag) return new Response(null, { status: 304, headers: { ETag: etag } });
    const body = serializeTodo(row);
    return new Response(request.method === "HEAD" ? null : body, {
      status: 200,
      headers: {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Length": String(new TextEncoder().encode(body).length),
        "ETag": etag,
        "Last-Modified": new Date(Number(row.updated_at) * 1000).toUTCString(),
        "Cache-Control": "no-store",
        "DAV": "1, 2, calendar-access"
      }
    });
  }
  if (request.method === "MKCALENDAR") {
    const calendarId = calendarIdFromPath(pathname);
    if (calendarId) {
      const existing = await getCalendar(env.DB, calendarId);
      if (existing) return new Response(null, { status: 204, headers: { "DAV": "1, 2, calendar-access" } });
      const body = await request.text();
      const displayMatch = body.match(/<(?:[A-Za-z0-9_-]+:)?displayname\b[^>]*>([\s\S]*?)<\/(?:[A-Za-z0-9_-]+:)?displayname>/i);
      const displayName = displayMatch
        ? displayMatch[1].replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").trim()
        : calendarId;
      await createCalendar(env.DB, calendarId, displayName || calendarId);
      return new Response(null, { status: 201, headers: { "DAV": "1, 2, calendar-access", "Location": HOME + encodeURIComponent(calendarId) + "/" } });
    }
    if (pathname === HOME || pathname === HOME.slice(0, -1)) {
      return new Response(null, { status: 201, headers: { "DAV": "1, 2, calendar-access" } });
    }
    return new Response("Collection not found", { status: 409 });
  }
  if (request.method === "MKCOL") {
    if (pathname === HOME || pathname === HOME.slice(0, -1)) {
      return new Response(null, { status: 201, headers: { "DAV": "1, 2, calendar-access" } });
    }
    return new Response("Use MKCALENDAR for calendar collections", { status: 405 });
  }
  if (request.method === "PROPPATCH") {
    const href = pathname.endsWith("/") ? pathname : pathname + "/";
    return xmlResponse(207, multistatus([responseNode(href, "")]));
  }
  return new Response("Method not supported", {
    status: 405, headers: { "Allow": "OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, REPORT, PROPPATCH, MKCOL, MKCALENDAR" }
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/.well-known/caldav") {
      return Response.redirect(url.origin + DAV_ROOT + "/", 301);
    }
    if (url.pathname === "/setup" || url.pathname === "/setup/") {
      return new Response("<!doctype html><meta name=viewport content=width=device-width><title>JARVIS Reminders</title><p>Open the private setup link shown in JARVIS Plugin Settings after testing the Cloudflare connection.</p>", {
        headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" }
      });
    }
    const setupToken = String(env.SETUP_TOKEN || "");
    const privateSetupPrefix = "/setup/" + setupToken;
    if (setupToken.length >= 32 && url.pathname === privateSetupPrefix && request.method === "GET") {
      if (!env.CALDAV_PASSWORD) return new Response("CalDAV password is not configured.", { status: 503 });
      return new Response(setupPage(url.origin, env.CALDAV_USERNAME || "jarvis", env.CALDAV_PASSWORD), {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store, no-cache, must-revalidate",
          "Pragma": "no-cache",
          "Referrer-Policy": "no-referrer",
          "X-Content-Type-Options": "nosniff"
        }
      });
    }
    if (setupToken.length >= 32 && url.pathname === privateSetupPrefix + "/JARVIS.mobileconfig" && request.method === "GET") {
      const profile = profileXml(url.host);
      return new Response(profile, {
        headers: {
          "Content-Type": "application/x-apple-aspen-config",
          "Content-Disposition": 'attachment; filename="JARVIS-Reminders.mobileconfig"',
          "Cache-Control": "no-store, no-cache, must-revalidate",
          "Pragma": "no-cache",
          "Referrer-Policy": "no-referrer",
          "X-Content-Type-Options": "nosniff"
        }
      });
    }
    if (url.pathname.startsWith("/api/")) return handleApi(request, env, url);
    if (url.pathname === "/" && ["PROPFIND", "OPTIONS"].includes(request.method)) {
      return handleDav(request, env, url);
    }
    if (
      ["/principals", "/principals/", "/calendar/dav/jarvis/user", "/calendar/dav/jarvis/user/"].includes(url.pathname) &&
      ["PROPFIND", "OPTIONS"].includes(request.method)
    ) {
      return handleDav(request, env, url);
    }
    if (url.pathname === DAV_ROOT || url.pathname.startsWith(DAV_ROOT + "/")) {
      return handleDav(request, env, url);
    }
    return jsonResponse(404, { error: "Not found." });
  }
};

export { parseTodo, parseDue, serializeTodo, validId, calendarIdFromPath, resourceInfo, discoveryRootProps, isPrincipalDiscoveryPath, principalProps, principalMissingPropstat, profileXml };
