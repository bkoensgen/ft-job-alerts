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
- Export is primary. For background runs: `python run.py run-daily --keywords "ros2,c++,vision" --commune 68224 --distance-km 50`.
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

Most useful commands
- Check OAuth config and token:
  - `python run.py auth-check`
- Nationwide, last 31 days, iterate pages (100/page up to 20 pages):
  - `python run.py fetch --keywords "robotique" --published-since-days 31 --limit 100 --all --max-pages 20`
- Radius around Mulhouse (INSEE 68224), 50 km, last 14 days:
  - `python run.py fetch --keywords "robotique" --commune 68224 --distance-km 50 --published-since-days 14 --limit 100 --all --max-pages 10`
- Departments 68 and 67, last 31 days:
  - `python run.py fetch --keywords "robotique" --dept 68,67 --published-since-days 31 --limit 100 --all --max-pages 10`
- Enrich with full descriptions + apply URL (detail endpoint):
  - `python run.py enrich --days 31 --only-missing-description --limit 500 --sleep-ms 200`
- Keyword sweep (OR, consolidate DB):
  - `python run.py sweep --keywords-list "robotique;robot;ros2;ros;automatisme;cobot;vision;ivvq;agv;amr" --published-since-days 31 --limit 100 --all --max-pages 20`
- Export for AI analysis (Markdown, full description):
  - `python run.py export --format md --days 31 --min-score 2.0 --top 200 --desc-chars -1`
  - TXT/MD exports include simple labels and tags (CORE_ROBOTICS, SENIORITY, REMOTE, PLC tags, sensors, adjacent categories).
  - Extra tags now include ROS stack (ros2, moveit, nav2, tf2, urdf, pcl…), robot brands (Fanuc/KUKA/ABB/Stäubli/UR/Yaskawa…), and vision libs (OpenCV/Halcon/Cognex/Keyence).
- Export CSV (full fields) and JSONL:
  - `python run.py export --format csv --days 31 --outfile data/out/offres.csv`
  - `python run.py export --format jsonl --days 31 --outfile data/out/offres.jsonl`

One-shot pipelines
- Daily (France entière par défaut), fetch → enrich → export:
  - `python run.py pipeline daily --keywords "robotique" --published-since-days 31 --limit 100 --max-pages 10 --export-top 200 --export-format md --desc-chars -1`
  - Localisation en option: `--commune 68224 --distance-km 50` ou `--dept 68,67`
- Weekly (couverture large), sweep → enrich → export → stats → nlp-stats:
  - `python run.py pipeline weekly --keywords-list "robotique;robot;ros2;ros;automatisme;cobot;vision;ivvq;agv;amr" --published-since-days 31 --limit 100 --max-pages 20 --export-top 300 --desc-chars -1`
  - Produit aussi: `data/out/keyword-stats.csv`, `data/out/tokens.csv`, `data/out/bigrams.csv`
  - Watchlist companies: `data/out/watchlist_companies.csv`

Keyword stats
- Global stats on given keywords over the current selection (last 31 days here):
  - `python run.py stats --keywords-list "ros2;ros;robotique;automatisme;vision;opencv;slam;moveit;gazebo;c++" --days 31`
  - Add per-department breakdown: `--group-by dept`
- Save to CSV: `--outfile data/out/keyword-stats.csv`
  
Company watchlist
- Top companies by number of offers in a time window:
  - `python run.py watchlist --days 31 --outfile data/out/watchlist_companies.csv`

Charts and dashboards (PNGs + CSVs)
- Generate charts from the current selection (uses matplotlib if available, else ASCII + CSV):
  - `python run.py charts --days 31 --outdir data/out/charts`
- Produces:
  - Bar charts + CSVs: departments, top companies, contracts, weekly timeline, ROS stack tags, robot brands, vision libs, languages, PLC tags.
  - If matplotlib isn’t installed, ASCII bar charts are written alongside CSVs.

Semantic-ish stats (automatic discovery)
- Compute distinctive tokens and bigrams for robotics offers (CORE_ROBOTICS) vs others using log-odds:
  - `python run.py nlp-stats --days 31 --top 40`
- Save CSVs:
  - `python run.py nlp-stats --days 31 --top 60 --outfile-tokens data/out/tokens.csv --outfile-bigrams data/out/bigrams.csv`
- Tip: fill the DB broadly first (use `sweep`) for better signal.
- Noise control:
  - Prune ubiquitous/rare terms: `--min-df 0.005 --max-df 0.4` (defaults).
  - Add custom stopwords: `--stop-add "poste;profil;mission;client;vous;h/f;cdi;interim"`.

Broaden results (keyword sweep)
- Run several fetches (they merge in DB):
  - `robotique`, `robot`, `ROS`, `automatisme`, `automatisation`, `cobot`, `vision`, `AGV`, `AMR`
- Example (nationwide, 31 days, 100/page, all pages):
  - `python run.py fetch --keywords "robot" --published-since-days 31 --limit 100 --all --max-pages 20`
  - `python run.py fetch --keywords "automatisme" --published-since-days 31 --limit 100 --all --max-pages 20`
  - `python run.py fetch --keywords "vision" --published-since-days 31 --limit 100 --all --max-pages 20`

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
  - `FT_SCOPE=application_${FT_CLIENT_ID} api_offresdemploiv2 o2dsoffre` (ou la valeur exacte fournie par l’habilitation)
- Optionally set `EMAIL_TO` and `SMTP_*` to receive email instead of text files.
- Run: `python run.py run-daily --keywords "ros2,c++,vision" --dept 68 --radius-km 50 --auto-rome`

If you hit 400 Bad Request on token
- Check `FT_SCOPE` is present and matches your habilitation (e.g., `application_{client_id} api_offresdemploiv2 o2dsoffre`).
- The CLI now surfaces the OAuth error body to help diagnose.

Search tips (Offres v2)
- Use `--commune <INSEE>` + `--distance-km N` for a radius search (the API ignores distance without commune).
- Or use `--dept 68,67` for department filters (no radius).
- Sorting: `--sort 0|1|2` where 1=date desc (default), 0=pertinence/date, 2=distance/pertinence.
- Pagination: `--page P` and `--limit L` map to `range=P*L-(P*L+L-1)` (L max 150). Use `--all --max-pages N` to iterate pages automatically.
- `publieeDepuis` (days): allowed values are 1, 3, 7, 14, 31. The CLI auto-snaps invalid values to the nearest allowed.
- Debugging 400:
  - Set `FT_DEBUG=1` to print the request URL.
  - If needed, set `FT_RANGE_HEADER=1` to send `Range: start-end` header instead of `range` query.

Nationwide examples
- Last 31 days, all France, iterate pages:
  - `python run.py fetch --keywords "robotique" --published-since-days 31 --limit 100 --all --max-pages 20`
- Radius around Mulhouse (INSEE 68224), 50 km:
  - `python run.py fetch --keywords "robotique" --commune 68224 --distance-km 50 --published-since-days 14 --limit 100 --all --max-pages 10`
