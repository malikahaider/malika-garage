# Malika Garage Platform

Responsive garage booking and shop operations app customized for Malika.
The app includes a customer directory and booking flow, role-specific shop workspaces,
booking history, estimate review, inventory receiving, QC issue loop, and seeded demo data.

## Run locally

Requirements: Python 3.10 or newer. No third-party packages or database server are needed.

Windows PowerShell:

```powershell
cd .\outputs\bayflow-website
Copy-Item .env.example .env
.\run.ps1
```

Or run the app directly:

```powershell
python .\server.py
```

Then open <http://localhost:8000>. The first run creates `bayflow.sqlite3` and seeds three
shops, their teams, sample inventory, and one example customer booking. Set `PORT` to use
another port. To start with clean demo data, stop the app and remove `bayflow.sqlite3`.

## Demo accounts

All demo accounts use password `Bayflow2026!`.

| Role | Email |
| --- | --- |
| Owner | `owner@bayflow.demo` |
| Service Advisor | `advisor@bayflow.demo` |
| Technician | `tech@bayflow.demo` |
| QC Inspector | `qc@bayflow.demo` |
| Parts Person | `parts@bayflow.demo` |
| Customer | `customer@bayflow.demo` |

The sign-in page has role shortcuts that fill the demo credentials.

## Included workflow

Customers can create accounts, browse shops, select services and appointment times, submit
vehicle details, track booking history, and approve or reject an estimate. Advisors confirm
and assign bookings, review estimates, and close ready pickups. Technicians inspect jobs,
submit itemized estimates, repair, and send work to QC. Parts staff record orders, receive
stock, and allocate parts. QC staff pass work or record issues that return jobs to repair.
Invalid state changes and cross-shop staff access are rejected by the API.

The demo provides a fixed sample service catalog, seeded sample inventory, and date/time slot
picker with capacity checks. Email/SMS, provider-based telephone calling, AI front desk,
payments, and public deployment are not configured.

## Project layout

- `server.py` — Python standard-library HTTP server, SQLite schema/seed, authentication,
  shop-scoped API and workflow rules.
- `index.html`, `styles.css`, `app.js` — responsive customer portal and role dashboards.
- `run.ps1` — starts the local server.
- `.env.example` — environment variable template.

## Configuration and deployment

Copy `.env.example` to `.env` and set the corresponding environment variables in your shell
or hosting platform. The server reads environment variables directly; it does not parse `.env`.
For a public production deployment, use HTTPS, a strong private `BAYFLOW_PASSWORD_PEPPER`,
managed persistent database backups, secure cookie/session handling, rate limiting, and a
production database such as PostgreSQL. The included app is a complete local demo build and
needs those deployment controls and an external hosting account before it can be treated as
a production service. No secrets are included.
