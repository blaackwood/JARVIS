import fs from "node:fs";
import dns from "node:dns";
dns.setDefaultResultOrder("ipv4first");

const vars = Object.fromEntries(fs.readFileSync(".dev.vars", "utf8").trim().split(/\r?\n/).map((line) => {
  const i = line.indexOf("=");
  return [line.slice(0, i), line.slice(i + 1)];
}));
const origin = process.env.JARVIS_ORIGIN || "http://127.0.0.1:8787";
const admin = { Authorization: "Bearer " + vars.JARVIS_ADMIN_TOKEN, "Content-Type": "application/json" };
const basic = { Authorization: "Basic " + Buffer.from(vars.CALDAV_USERNAME + ":" + vars.CALDAV_PASSWORD).toString("base64") };
function assert(ok, message) { if (!ok) throw new Error(message); }
async function call(path, init = {}) {
  const response = await fetch(origin + path, init);
  const body = await response.text();
  return { response, body };
}
const health = await call("/api/health", { headers: admin });
assert(health.response.status === 200 && JSON.parse(health.body).server === "jarvis-cloudflare", "admin health endpoint");
const denied = await call("/api/health");
assert(denied.response.status === 401, "admin endpoint rejects unauthenticated calls");
const davDenied = await call("/dav/");
assert(davDenied.response.status === 401, "CalDAV challenges without Basic auth");
const setupResponse = await call("/api/setup", { headers: admin });
assert(setupResponse.response.status === 200, "private setup metadata");
const setup = JSON.parse(setupResponse.body);
const profilePath = new URL(setup.setup_profile_url).pathname;
const credentialPath = new URL(setup.credentials_url).pathname;
const publicProfile = await call("/setup/JARVIS.mobileconfig");
assert(publicProfile.response.status === 404, "iOS profile is not public");
const profile = await call(profilePath);
assert(profile.response.status === 200 && profile.body.includes("com.apple.caldav.account"), "private iOS profile payload");
assert(!profile.body.includes(vars.CALDAV_PASSWORD), "profile does not embed the CalDAV password");
const credentials = await call(credentialPath);
assert(credentials.response.status === 200 && credentials.body.includes(vars.CALDAV_PASSWORD), "private setup page reveals the account password only at its token URL");
assert(credentials.response.headers.get("cache-control").includes("no-store"), "private credentials page is not cached");

const id = "smoke-phone-123";
const todo = [
  "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VTODO",
  "UID:" + id, "DTSTAMP:20261116T180000Z",
  "SUMMARY:Smoke test reminder", "DUE:20261120T150000Z",
  "STATUS:NEEDS-ACTION", "END:VTODO", "END:VCALENDAR", ""
].join("\r\n");
const put = await call("/dav/calendars/jarvis/JARVIS/" + id + ".ics", {
  method: "PUT", headers: { ...basic, "Content-Type": "text/calendar; charset=utf-8" }, body: todo
});
assert([201, 204].includes(put.response.status), "CalDAV PUT creates VTODO: " + put.response.status);
const props = await call("/dav/calendars/jarvis/JARVIS/", {
  method: "PROPFIND", headers: { ...basic, Depth: "1", "Content-Type": "application/xml" },
  body: '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:allprop/></d:propfind>'
});
assert(props.response.status === 207 && props.body.includes(id + ".ics"), "PROPFIND lists calendar item");
const report = await call("/dav/calendars/jarvis/JARVIS/", {
  method: "REPORT", headers: { ...basic, "Content-Type": "application/xml" },
  body: '<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>'
});
assert(report.response.status === 207 && report.body.includes("Smoke test reminder"), "CalDAV REPORT returns VTODO");
const api = await call("/api/reminders", { headers: admin });
const items = JSON.parse(api.body).reminders;
assert(items.some((item) => item.id === id && item.message === "Smoke test reminder" && item.due_ts > 0), "D1 API sees phone-created reminder");
const completed = todo.replace("Smoke test reminder", "Smoke test updated").replace("NEEDS-ACTION", "COMPLETED");
const syncTokenBeforeUpdate = (props.body.match(/<d:sync-token>(.*?)<\/d:sync-token>/) || [])[1];
assert(syncTokenBeforeUpdate, "calendar exposes a sync token");
const putDone = await call("/dav/calendars/jarvis/JARVIS/" + id + ".ics", {
  method: "PUT", headers: { ...basic, "Content-Type": "text/calendar; charset=utf-8" }, body: completed
});
assert([201, 204].includes(putDone.response.status), "CalDAV update VTODO");
const delta = await call("/dav/calendars/jarvis/JARVIS/", {
  method: "REPORT", headers: { ...basic, "Content-Type": "application/xml" },
  body: '<?xml version="1.0"?><d:sync-collection xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:sync-token>' +
    syncTokenBeforeUpdate + '</d:sync-token><d:sync-level>1</d:sync-level><d:prop><d:getetag/><c:calendar-data/></d:prop></d:sync-collection>'
});
assert(delta.response.status === 207 && delta.body.includes("Smoke test updated"), "sync-collection reports changed VTODOs");
const syncTokenAfterUpdate = (delta.body.match(/<d:sync-token>(.*?)<\/d:sync-token>/) || [])[1];
assert(syncTokenAfterUpdate, "sync-collection returns the next token");
const afterDone = await call("/api/reminders", { headers: admin });
const doneItem = JSON.parse(afterDone.body).reminders.find((item) => item.id === id);
assert(doneItem?.status === "done" && doneItem.message === "Smoke test updated", "completion flows into D1");
const deleted = await call("/dav/calendars/jarvis/JARVIS/" + id + ".ics", { method: "DELETE", headers: basic });
assert(deleted.response.status === 204, "CalDAV DELETE");
const deletionDelta = await call("/dav/calendars/jarvis/JARVIS/", {
  method: "REPORT", headers: { ...basic, "Content-Type": "application/xml" },
  body: '<?xml version="1.0"?><d:sync-collection xmlns:d="DAV:"><d:sync-token>' +
    syncTokenAfterUpdate + '</d:sync-token><d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>'
});
assert(deletionDelta.response.status === 207 && deletionDelta.body.includes("404 Not Found"), "sync-collection sends tombstone for deleted VTODO");
const afterDelete = await call("/api/reminders", { headers: admin });
const cancelled = JSON.parse(afterDelete.body).reminders.find((item) => item.id === id);
assert(cancelled?.status === "cancelled", "delete becomes cancellation instead of erasing sync history");
console.log("PASS: Cloudflare Worker API auth, iOS profile, CalDAV Basic auth, PUT, PROPFIND, REPORT, D1 sync, completion and deletion.");
