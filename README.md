# Jack's Wellness Protocol App

A personal wellness tracker built on Flask + SQLite, deployed on Railway with persistent storage.

## Stack

- **Backend**: Python / Flask
- **Database**: SQLite (persisted via Railway Volume at `/data/wellness.db`)
- **Frontend**: Vanilla JS, Chart.js, served via Flask templates
- **Hosting**: Railway
- **Updates**: Push to GitHub → Railway auto-deploys

---

## How Updates Work

This app is designed so that protocol changes (new items, modified notes, new sections)
can be made by editing `app.py` → `SECTIONS` dict and pushing to GitHub.
Railway auto-deploys within ~2 minutes. No database migration needed for protocol changes
since the protocol is served as JSON from the API on every page load.

### To update the protocol:
1. Edit the `SECTIONS` list in `app.py`
2. Bump `PROTOCOL_VERSION` (e.g. `"1.3.0"` → `"1.4.0"`)
3. Update `PROTOCOL_NOTES` with a description of changes
4. `git add . && git commit -m "Protocol update: [description]" && git push`
5. Railway deploys automatically in ~2 minutes
6. The app shows the new version number in the nav bar

---

## Local Development

```bash
pip install -r requirements.txt
DB_PATH=./wellness.db python app.py
# Open http://localhost:5000
```

---

## Railway Deployment

### First-time setup:
1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select this repo
4. Add a Volume: Settings → Volumes → Mount Path: `/data`
5. Set environment variable: `DB_PATH=/data/wellness.db`
6. Deploy — Railway picks up `railway.toml` automatically

### Auto-deploy:
Railway is connected to GitHub. Every push to `main` triggers a new deploy.
The SQLite database persists in the Volume across deploys.

---

## Environment Variables

| Variable | Value | Notes |
|----------|-------|-------|
| `DB_PATH` | `/data/wellness.db` | Set in Railway dashboard |
| `PORT` | Auto-set by Railway | Do not override |

---

## File Structure

```
jack-wellness/
├── app.py              ← Flask app + PROTOCOL definition (edit this to update)
├── requirements.txt
├── Procfile
├── railway.toml        ← Railway config with Volume mount
├── nixpacks.toml       ← Build config
├── templates/
│   └── index.html      ← Full frontend (HTML/CSS/JS)
└── static/             ← Optional static assets
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve the app |
| GET | `/api/protocol` | Current protocol definition (sections, items, levels) |
| GET | `/api/today` | Today's log entry |
| POST | `/api/today` | Save today's log |
| GET | `/api/history?limit=N` | All historical entries |
| GET | `/api/stats` | Aggregate statistics |
| GET | `/api/chart/completion?days=N` | Completion data for chart |
| GET | `/api/chart/mood?days=N` | Mood data for chart |
| GET | `/api/version` | Current version info |
| GET | `/health` | Health check for Railway |

---

## Gamification System

- **XP** earned per checked item (varies by section importance)
- **12 Levels** from "Beginning" to "Protocol Master"
- **Streak** tracking: consecutive days with ≥50% completion
- **10 Achievement Badges** stored in browser localStorage

---

*Protocol v1.3.0 — MTHFR C677T homozygous · OCD & Depression support*
