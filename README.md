# Transmission Console — YouTube Automation Tool

A private, two-operator control panel that auto-uploads videos to YouTube on a
schedule, sends Telegram notifications, and tracks engagement + analytics.
Everything here runs on free / open-source software.

- **Backend:** Python + Flask
- **Database:** either **Supabase (cloud)** or **local MySQL** — you pick with one setting
- **Scheduler:** APScheduler with automatic catch-up (missed uploads run on wake)
- **Storage:** Supabase Storage bucket (cloud) or a local folder (local)

---

## 1. What you need first

1. **Python 3.10+** installed.
2. One of:
   - a **Supabase** project (free tier), *or*
   - **MySQL** installed locally (MySQL Community Server, free).
3. A **Google Cloud** project with the YouTube APIs enabled (free).
4. A **Telegram bot** (free, via @BotFather) — optional but recommended.

---

## 2. Install

```bash
cd yt-automation
python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Create your `.env`

Copy the example and open it in a text editor:

```bash
cp .env.example .env
```

Generate the two security keys and paste them into `.env`:

```bash
# SECRET_KEY
python -c "import secrets;print(secrets.token_hex(32))"

# FERNET_KEY
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

Then fill in the rest of `.env` (details below).

### Choose your database

```
DB_MODE=local     # local MySQL + local disk  (best when offline / lots of video)
DB_MODE=cloud     # Supabase Postgres + Supabase Storage bucket
```

You can switch anytime by changing this one line and restarting.

#### If `DB_MODE=local` (MySQL)
1. Create the database once:
   ```sql
   CREATE DATABASE yt_automation CHARACTER SET utf8mb4;
   ```
2. Fill `MYSQL_HOST / PORT / USER / PASSWORD / DB` in `.env`.
   Video files are saved under `storage/videos/` (change with `LOCAL_STORAGE_DIR`).

#### If `DB_MODE=cloud` (Supabase)
1. In your Supabase project: **Project Settings → Database** → copy the URI and
   put it in `SUPABASE_DB_URL` (keep the `postgresql+psycopg2://` prefix shown
   in `.env.example`).
2. **Project Settings → API** → copy the project URL and the **service_role**
   key into `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
3. Set `SUPABASE_BUCKET=videos` (the app creates the bucket if missing).

### Your two operator accounts

```
ADMIN1_USERNAME=Cipher
ADMIN1_PASSWORD=...        # login password
ADMIN1_SAFEWORD=...        # separate word, required to change credentials

ADMIN2_USERNAME=Lucifer
ADMIN2_PASSWORD=...
ADMIN2_SAFEWORD=...
```

Passwords and safe words are **never stored as plain text** — they're bcrypt-hashed
on first run. To change them later, edit `.env` and restart; the app re-hashes
automatically.

---

## 4. Set up YouTube (Google Cloud)

1. Go to <https://console.cloud.google.com/> → create/select a project.
2. **APIs & Services → Library** → enable **YouTube Data API v3** *and*
   **YouTube Analytics API**.
3. **APIs & Services → OAuth consent screen** → set it up (External is fine),
   and add both of your Google accounts as **Test users**.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Web application.** Add this Authorized redirect URI exactly:
   ```
   http://localhost:5000/integrations/youtube/callback
   ```
   (If you run on a server with a domain, add that version too.)
5. Copy the **Client ID** and **Client secret** into `.env`
   (`YT_CLIENT_ID`, `YT_CLIENT_SECRET`).

> **About public uploads (important):** Google forces videos uploaded through the
> API to stay **private** until your project passes a one-time review. That review
> is **free**. Until you're approved, keep `YT_DEFAULT_PRIVACY=private`. Once
> approved, change it to `public` (or set privacy per video) and uploads publish
> live automatically — no code changes needed.

---

## 5. Set up Telegram (optional)

1. Message **@BotFather** on Telegram → `/newbot` → copy the token into
   `TELEGRAM_BOT_TOKEN`.
2. Message your new bot once, then open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and copy the numeric
   `chat.id` into `TELEGRAM_CHAT_ID`.

---

## 6. Run it

```bash
python app.py
```

Open <http://localhost:5000> and sign in with one of your operator accounts.
Then go to **Integrations → Connect / re-authorize YouTube** and approve access.

That's it — add videos, schedule them, and the console handles the rest.

---

## 7. Keeping it running

The scheduler checks for due uploads **every 60 seconds** and reads its queue
from the database, so:

- If the machine sleeps through a scheduled time, that upload runs on the next
  check after it wakes — nothing is lost.
- A restart never loses the queue (it lives in the database, not memory).

**On a laptop:** just leave the app running (and ideally stop the machine from
sleeping around upload times).

**On an always-on Linux server**, run it as a service. Example `systemd` unit
(`/etc/systemd/system/transmit-yt.service`):

```ini
[Unit]
Description=Transmission Console (YouTube automation)
After=network.target

[Service]
WorkingDirectory=/path/to/yt-automation
ExecStart=/path/to/yt-automation/venv/bin/python app.py
Restart=always
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now transmit-yt
```

---

## 8. Feature map

| Page | What it does |
|------|--------------|
| **Dashboard** | Tiles (Total / In queue / Published / Storage) that drill into lists; near-real-time engagement with a Refresh button; recent videos; activity log with Prev/Next. |
| **Videos** | Tabs for All / Scheduled / Uploaded / Upload failed (with error logs). Add, edit, delete. Import/export as `.xlsx`. |
| **Schedule** | *By day* — pick a date and schedule videos individually. *By slots* — define times like 08:00 / 12:00 / 18:00 and drop a batch in; they fill in order and roll to the next day. |
| **Analytics** | Daily / weekly / monthly / yearly presets, a custom date range, and specific (non-contiguous) day selection. |
| **Integrations** | Edit YouTube / Telegram / Supabase credentials — **each change requires your safe word.** Connect YouTube. Pause/resume the scheduler. |
| **Settings** | See the two operators and the active database mode. |

---

## 9. Security notes

- Login passwords and safe words → bcrypt hashes.
- API tokens/keys → encrypted at rest with your `FERNET_KEY`.
- The OAuth token is stored encrypted in the database, never on disk in plain text.
- Never commit your real `.env` anywhere public.

---

## 10. Common issues

- **`FERNET_KEY is not set`** — you skipped the key generation step in section 3.
- **`DB_MODE=cloud but SUPABASE_DB_URL is empty`** — fill the Supabase URI, or set `DB_MODE=local`.
- **MySQL connection refused** — MySQL isn't running, or host/port/user/password are wrong.
- **YouTube uploads stay private** — expected until Google's free audit passes (section 4).
- **`redirect_uri_mismatch` when connecting YouTube** — the redirect URI in Google Cloud must match `YT_REDIRECT_URI` exactly.
