ft-job-alerts — France Travail job extraction (robotics/ROS2)

Overview
- Automates daily retrieval, filtering, scoring, and notification of job offers for a junior robotics profile (ROS 2 / C++ / vision), locally (68) and France-wide.
- Stores offers in SQLite, tracks applications, and schedules follow-ups (J+5 / J+12).

What’s included
- Minimal Python pipeline (stdlib only): OAuth client (stub), Offres d’emploi v2 client (stub + simulate mode), filters, scoring, SQLite storage, exporter (txt/csv/md/jsonl), optional notifier, and a CLI.
- A sample dataset for offline testing (no network required).

Quick start
1) Python 3.10+ recommended. Create a virtualenv (optional). Env vars can be put in `.env` (auto‑loaded) — see `.env.example`. At minimum:
   - FT_CLIENT_ID / FT_CLIENT_SECRET (from your habilitation)
   - Prefer running in simulate mode first: FT_API_SIMULATE=1

2) Initialize DB and run once in simulate mode (no install needed):
   - python run.py init-db
   - python run.py fetch --keywords "ros2,c++,vision" --dept 68 --radius-km 50
   - python run.py export --format txt --days 7 --top 50 --desc-chars 500  # writes under data/out/

3) Inspect output
   - SQLite DB at data/ft_jobs.db
   - Notifications written under data/out/ (in simulate mode without SMTP config)

Daily usage (optional)
- Export is primary. For background runs: `python run.py run-daily --keywords "ros2,c++,vision" --dept 68 --radius-km 50`.
- Daily run does: fetch (or simulate), filter/score, store new offers, and optionally send a summary notification. It also includes due follow-ups (J+5/J+12) if you’ve marked offers as applied.

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

Export usage (analysis-friendly)
- Export last 7 days, top 50 by score to TXT with descriptions:
  - `python run.py export --format txt --days 7 --top 50 --desc-chars 500`
- Export to CSV for spreadsheets (full fields):
  - `python run.py export --format csv --days 14 --outfile data/out/offres.csv`
- Export to Markdown (copy/paste into GPT) with descriptions:
  - `python run.py export --format md --days 7 --min-score 2.0 --top 30 --desc-chars 600`
- Export JSONL (idéal pour pipelines IA):
  - `python run.py export --format jsonl --days 7 --outfile data/out/offres.jsonl`

Get full descriptions (real API)
- After fetching IDs, run enrichment to pull full details (description, apply URL, salary) via the offer detail endpoint:
  - `python run.py enrich --days 7 --only-missing-description --limit 100 --sleep-ms 250`
- For specific offers:
  - `python run.py enrich --ids OFFER123,OFFER456`
- Then export with full descriptions (no truncation):
  - `python run.py export --format md --days 7 --min-score 2.0 --top 30 --desc-chars -1`

Filtering flags
- `--days N` (relative window on inserted_at) or `--from 2025-09-01 --to 2025-09-12`
- `--status new|applied|rejected|to_follow` (optional)
- `--min-score FLOAT` and `--top N`
- `--desc-chars N` controls how many characters of description are included in txt/md (0 to omit)

Enabling real API calls (when ready)
- Put in `.env` (auto‑loaded) or export in your shell:
  - `FT_API_SIMULATE=0`
  - `FT_CLIENT_ID=...`
  - `FT_CLIENT_SECRET=...`
- Optionally set `EMAIL_TO` and `SMTP_*` to receive email instead of text files.
- Run: `python run.py run-daily --keywords "ros2,c++,vision" --dept 68 --radius-km 50 --auto-rome`
