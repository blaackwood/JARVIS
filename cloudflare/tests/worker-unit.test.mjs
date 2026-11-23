import test from "node:test";
import assert from "node:assert/strict";
import { parseTodo, serializeTodo, validId, calendarIdFromPath, resourceInfo, discoveryRootProps, isPrincipalDiscoveryPath, principalProps, principalMissingPropstat, profileXml } from "../src/index.js";

test("parses a timed VTODO and preserves the Brazil timezone", () => {
  const ics = [
    "BEGIN:VCALENDAR", "BEGIN:VTODO", "UID:reminder-001",
    "SUMMARY:Call the dentist", "DUE;TZID=America/Sao_Paulo:20261120T120000",
    "STATUS:NEEDS-ACTION", "DESCRIPTION:Bring\\, documents",
    "END:VTODO", "END:VCALENDAR"
  ].join("\r\n");
  const item = parseTodo(ics, "reminder-001", "UTC");
  assert.equal(item.message, "Call the dentist");
  assert.equal(item.status, "open");
  assert.equal(item.description, "Bring, documents");
  assert.ok(Math.abs(item.due_ts - Date.parse("2026-11-20T15:00:00Z") / 1000) < 1);
  assert.equal(item.date_only, false);
});

test("parses all-day VTODO dates without inventing a time", () => {
  const ics = [
    "BEGIN:VCALENDAR", "BEGIN:VTODO", "UID:all-day-1",
    "SUMMARY:Birthday", "DUE;VALUE=DATE:20261201",
    "STATUS:NEEDS-ACTION", "END:VTODO", "END:VCALENDAR"
  ].join("\r\n");
  const item = parseTodo(ics, "all-day-1", "America/Sao_Paulo");
  assert.equal(item.due_ts, null);
  assert.equal(item.due_raw, "20261201");
  assert.equal(item.date_only, true);
});

test("maps completed and cancelled states and safely escapes text", () => {
  const done = parseTodo([
    "BEGIN:VCALENDAR", "BEGIN:VTODO", "UID:done-1",
    "SUMMARY:Review\\, report", "STATUS:COMPLETED",
    "END:VTODO", "END:VCALENDAR"
  ].join("\r\n"), "done-1", "UTC");
  assert.equal(done.status, "done");
  assert.equal(done.message, "Review, report");
  const cancelled = parseTodo([
    "BEGIN:VCALENDAR", "BEGIN:VTODO", "UID:cancel-1",
    "SUMMARY:Old", "STATUS:CANCELLED",
    "END:VTODO", "END:VCALENDAR"
  ].join("\r\n"), "cancel-1", "UTC");
  assert.equal(cancelled.status, "cancelled");
});

test("serializes date-only reminders without assigning a clock time", () => {
  const ics = serializeTodo({
    id: "all-day-2", message: "Holiday", status: "open",
    due_ts: null, due_raw: "20261225", date_only: true, updated_at: 1790000000
  });
  assert.match(ics, /DUE;VALUE=DATE:20261225/);
  assert.doesNotMatch(ics, /DUE:\\d{8}T/);
});

test("restricts CalDAV resource identifiers", () => {
  assert.equal(validId("reminder_123-abc"), "reminder_123-abc");
  assert.equal(validId("phone.user@example.com"), "phone.user@example.com");
  assert.equal(validId("../outside"), "");
  assert.equal(validId(""), "");
});

test("publishes the CalDAV principal address and absolute calendar home", () => {
  const props = principalProps();
  assert.match(props, /<c:calendar-user-address-set><d:href>\/dav\/principals\/jarvis\//);
  assert.match(props, /<c:calendar-home-set><d:href>\/dav\/calendars\/jarvis\//);
});

test("returns explicit 404 propstat for unsupported principal properties", () => {
  const body = `<?xml version="1.0"?>
    <d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"
      xmlns:cs="http://calendarserver.org/ns/">
      <d:prop><c:calendar-user-address-set/><c:schedule-inbox-URL/>
        <c:schedule-outbox-URL/><cs:dropbox-home-URL/><d:resource-id/>
      </d:prop>
    </d:propfind>`;
  const missing = principalMissingPropstat(body);
  assert.match(missing, /HTTP\/1\.1 404 Not Found/);
  assert.match(missing, /<c:schedule-inbox-URL\/>/);
  assert.match(missing, /<c:schedule-outbox-URL\/>/);
  assert.match(missing, /<x:dropbox-home-URL xmlns:x="http:\/\/calendarserver\.org\/ns\/"\/>/);
  assert.doesNotMatch(missing, /calendar-user-address-set/);
  assert.doesNotMatch(missing, /resource-id/);
});

 
test("profile leaves PrincipalURL unset so iOS uses CalDAV discovery", () => {
  const profile = profileXml("jarvis-reminders.example.workers.dev");
  assert.match(profile, /<key>CalDAVHostName<\/key>/);
  assert.match(profile, /<key>CalDAVUseSSL<\/key><true\/>/);
  assert.doesNotMatch(profile, /CalDAVPrincipalURL/);
});

 
test("advertises the DAV root principal URL for discovery", () => {
  const props = discoveryRootProps();
  assert.match(props, /<d:current-user-principal><d:href>\/dav\/principals\/jarvis\//);
  assert.match(props, /<d:principal-URL><d:href>\/dav\/principals\/jarvis\//);
});

test("recognizes Apple CalDAV principal discovery aliases", () => {
  assert.equal(isPrincipalDiscoveryPath("/principals/"), true);
  assert.equal(isPrincipalDiscoveryPath("/calendar/dav/jarvis/user/"), true);
  assert.equal(isPrincipalDiscoveryPath("/dav/principals/jarvis/"), true);
  assert.equal(isPrincipalDiscoveryPath("/not-a-principal/"), false);
});

 
test("routes custom list collection paths and VTODO resources", () => {
  assert.equal(calendarIdFromPath("/dav/calendars/jarvis/Lembretes/"), "Lembretes");
  assert.equal(calendarIdFromPath("/dav/calendars/jarvis/JARVIS/"), "JARVIS");
  assert.equal(calendarIdFromPath("/dav/calendars/jarvis/"), "");
  assert.deepEqual(resourceInfo("/dav/calendars/jarvis/Lembretes/tests-jarvis.ics"), {
    calendarId: "Lembretes",
    id: "tests-jarvis"
  });
  assert.equal(resourceInfo("/dav/calendars/jarvis/Lembretes/../outside.ics"), null);
});
