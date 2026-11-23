# JARVIS Reminders on Cloudflare

This folder contains the Cloudflare Worker + D1 implementation of the JARVIS CalDAV endpoint. It is independent of the old Python/Radicale server, so the user's PC does not need to stay online for Apple Reminders to reach the cloud calendar.

## What it provides

- HTTPS CalDAV endpoint for Apple Reminders on the Cloudflare workers.dev hostname.
- D1-backed persistent VTODO items.
- Basic authentication for the iPhone account.
- Separate Bearer-token API for the JARVIS desktop connector.
- A password-free iOS configuration profile behind a private random setup URL.
- Completion, title, due-time and delete/cancel updates through CalDAV.
- A D1 change journal for incremental sync-collection responses and deletion tombstones.
- A desktop API that exposes phone-created reminders to the existing JARVIS reminders store.

The Worker supports one-shot VTODO reminders with a timed due date or date-only due date. Recurrence, subtasks, attachments, locations, alarms and advanced calendar features are not implemented yet.

## Local validation

Node.js 24 and Wrangler 4 are used. In this directory:

    npm install
    npx wrangler d1 migrations apply jarvis-reminders --local

Create local-only secrets in .dev.vars (this file is ignored by Git):

    JARVIS_ADMIN_TOKEN=<random token, at least 32 characters>
    CALDAV_USERNAME=jarvis
    CALDAV_PASSWORD=<random password, at least 24 characters>
    SETUP_TOKEN=<random token, at least 32 characters>
    DEFAULT_TIMEZONE=America/Sao_Paulo

Then start the local Worker:

    npx wrangler dev --local --port 8787 --ip 127.0.0.1

In another terminal:

    node smoke.mjs
    npm test

To run the same end-to-end smoke test against the deployed Worker (PowerShell):

    $env:JARVIS_ORIGIN = "https://jarvis-reminders.<your-workers-subdomain>.workers.dev"
    npm run test:smoke

The smoke client prefers IPv4 so it also works on Windows networks that publish an IPv6 DNS record without a working IPv6 route.

## First deployment

1. Authenticate Wrangler against the user's Cloudflare account with npx wrangler login --device.
2. Create the D1 database: npx wrangler d1 create jarvis-reminders.
3. Copy the returned database UUID into wrangler.toml, replacing REPLACE_WITH_D1_DATABASE_ID.
4. Apply the schema: npx wrangler d1 migrations apply jarvis-reminders --remote.
5. Upload all five production secrets from the local-only .dev.vars file: npx wrangler secret bulk .dev.vars. This creates JARVIS_ADMIN_TOKEN, CALDAV_USERNAME, CALDAV_PASSWORD, SETUP_TOKEN and DEFAULT_TIMEZONE. The setup token protects both the iOS profile and the private page that displays the CalDAV password.
6. Deploy with npm run deploy.

Do not put production credentials in source files, commit them, or send them in chat. The desktop connector's worker_token must match JARVIS_ADMIN_TOKEN; the iPhone CalDAV password must match CALDAV_PASSWORD.

## JARVIS desktop connector

In JARVIS > Settings > Plugin Settings > JARVIS cloud link, fill:

- Cloudflare Worker HTTPS URL: the URL Wrangler prints after deployment, e.g. https://jarvis-reminders.<workers-subdomain>.workers.dev.
- Cloudflare JARVIS API token: the value stored as JARVIS_ADMIN_TOKEN.

Keep the legacy pinned-TLS pairing code empty when using the Cloudflare Worker. The existing desktop reminder store and HUD remain the canonical local UI; this connector only mirrors the cloud copy and imports phone-created reminders.

## iPhone

Open the private setup profile link shown in JARVIS Plugin Settings on the iPhone and install the JARVIS Reminders profile. The setup page link displays the CalDAV username and password. Enter them when iOS requests login credentials.

- Username: jarvis
- Password: the value stored as CALDAV_PASSWORD

The profile intentionally does not contain the password. The setup links contain a private random token and must not be shared. Cloudflare supplies publicly trusted HTTPS, so no self-signed root certificate profile is needed.

## Free-plan notes

Cloudflare Free limits apply. The Worker and D1 data persist between requests, but daily request/query limits are enforced. D1 free limits include 5 million rows read/day, 100,000 rows written/day, and 500 MB maximum per database. Monitor usage in Cloudflare; this is a starter deployment, not an SLA or an uptime guarantee.
