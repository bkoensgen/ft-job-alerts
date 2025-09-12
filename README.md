ft-job-alerts — France Travail job alerts (robotics/ROS2)

Overview
- Automates daily retrieval, filtering, scoring, and notification of job offers for a junior robotics profile (ROS 2 / C++ / vision), locally (68) and France-wide.
- Stores offers in SQLite, tracks applications, and schedules follow-ups (J+5 / J+12).

What’s included
- Minimal Python pipeline (stdlib only): OAuth client (stub), Offres d’emploi v2 client (stub + simulate mode), filters, scoring, SQLite storage, notifier (email or file/console), and a CLI.
- A sample dataset for offline testing (no network required).

Quick start
1) Python 3.10+ recommended. Create a virtualenv (optional) and set environment variables (see .env.example). At minimum:
   - FT_CLIENT_ID / FT_CLIENT_SECRET (from your habilitation)
   - Prefer running in simulate mode first: FT_API_SIMULATE=1

2) Initialize DB and run once in simulate mode (no install needed):
   - python run.py init-db
   - python run.py run-daily --keywords "ros2,c++,vision" --dept 68 --radius-km 50

3) Inspect output
   - SQLite DB at data/ft_jobs.db
   - Notifications written under data/out/ (in simulate mode without SMTP config)

Daily usage (cron/systemd)
- Run: python run.py run-daily --keywords "ros2,c++,vision" --dept 68 --radius-km 50
- This will: fetch (or simulate), filter/score, store new offers, and send a summary notification. It will also include due follow-ups (J+5/J+12) if you’ve marked offers as applied.

Follow-ups
- Mark an offer as applied:
  - python run.py set-status --offer-id <ID> --status applied
- The system computes follow-ups due dates J+5 and J+12 and reminds you in the next daily run.

Security note
- Do NOT commit secrets. Use environment variables or an untracked .env file. The repo only includes .env.example.

Configuration
- Env variables (see .env.example for the full list):
  - FT_API_SIMULATE=1 — use local sample data, no network.
  - FT_CLIENT_ID / FT_CLIENT_SECRET — OAuth2 client credentials.
  - FT_AUTH_URL, FT_OFFRES_SEARCH_URL — override endpoints if needed.
  - EMAIL_TO / SMTP_* — optional email notifications (otherwise writes to data/out and prints to console).

Endpoints (defaults — verify with current docs)
- OAuth2: https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire
- Offres search: https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search
- Offres detail: https://api.francetravail.io/partenaire/offresdemploi/v2/offres/{id}

Notes
- Network calls are disabled in this environment; simulate mode provides realistic flow. Replace simulate with real endpoints once credentials are set.
- ROME 4.0 and La Bonne Boîte clients are stubbed for now; provide codes via CLI/env, or later plug real APIs.

Enabling real API calls (when ready)
- Set `FT_API_SIMULATE=0`, and set `FT_CLIENT_ID` and `FT_CLIENT_SECRET` in your environment (don’t commit them).
- Optionally set `EMAIL_TO` and `SMTP_*` to receive email instead of text files.
- Run: `python run.py run-daily --keywords "ros2,c++,vision" --dept 68 --radius-km 50 --auto-rome`
