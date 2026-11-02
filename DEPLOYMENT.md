# Deploying AutoGMap, going back, and staging

The procedure for changing production (the standards review of 1 Nov 2026:
controlled deployment, rollback, incident response). Production is
`/home/mansi/AUTOGMAP` on the R730, served at https://indev.eko.in/autogmap/.
Everything here runs as root in that folder and touches nothing outside it
(staging lives beside it in `/home/mansi/AUTOGMAP-staging`).

## 1. Before deploying: CI must be green

Every push to `main` runs GitHub Actions (`.github/workflows/ci.yml`): the full
test suite, the golden set of bot conversations, and the frontend build. A
commit is ready for production only when both checks are green:
https://github.com/mansikanchan2003/G-Map-Data-Scraper/actions

For anything bigger than a small fix, try it on staging first (section 4).

## 2. Deploy

```bash
cd /home/mansi/AUTOGMAP && bash scripts/deploy.sh
```

`scripts/deploy.sh` does, in order, and stops at the first problem:

1. Checks GitHub that CI is green for the commit (`--without-ci` skips this
   when GitHub cannot be reached; check the Actions page yourself first).
2. Waits for the gap between scraping batches: it stops if a job is running.
3. Notes the commit running now in `.deploy/previous` (for rollback) and
   `.deploy/history`.
4. Pulls, builds the image, and runs the golden set on the new image. If the
   golden set fails, nothing has changed: the old backend is still running.
5. Backs the database up to `backups/before-<commit>-<time>.sql.gz`, then runs
   the migrations.
6. Starts the new backend and waits for `/health` to say healthy.

By hand, the same steps are: `git pull --ff-only`, `docker compose build
backend`, `docker compose run --rm backend python -m src.evals.golden --save`
(must pass), a `pg_dump` backup, `docker compose run --rm backend alembic
upgrade head`, `docker compose up -d backend`.

## 3. Going back

```bash
cd /home/mansi/AUTOGMAP && bash scripts/rollback.sh            # to the commit before the last deploy
cd /home/mansi/AUTOGMAP && bash scripts/rollback.sh <commit>   # to a commit you name
```

The code goes back; the database stays as it is. AutoGMap's migrations only
add tables and columns, so older code runs on a newer database. The next
`deploy.sh` returns to `main`.

### Restoring the database

Only when a migration itself damaged data, and only deliberately. It replaces
everything written since the backup, so stop the backend first and note the
time:

```bash
cd /home/mansi/AUTOGMAP && ls -lt backups/ | head
docker compose stop backend
gunzip -c backups/<the backup>.sql.gz | docker compose exec -T postgres psql -U gmap_user -d gmap_scraper
```

A `pg_dump` backup restores into an empty database. To restore over the live
one, first ask for help: dropping the database is irreversible.

## 4. Staging

A second copy of AutoGMap, with its own database, containers and settings, to
try a commit on before production. Nothing in it can message anyone or reach a
real service (`docker-compose.staging.yml`: WhatsApp mocked, no email, Drive,
DigiLocker, Kiosk KAI, scraping or background senders).

```bash
cd /home/mansi/AUTOGMAP && bash scripts/staging.sh            # the newest main
cd /home/mansi/AUTOGMAP && bash scripts/staging.sh <commit>   # a commit or branch
cd /home/mansi/AUTOGMAP && bash scripts/staging.sh --stop
```

The first run asks for a staging admin password and writes the staging
`.env` with new secrets (production's is never read). It answers only on the
server; from a laptop:

```bash
ssh -p 2222 -L 8100:127.0.0.1:8100 mansi@indev.eko.in
```

then open http://localhost:8100.

## 5. When something goes wrong

- **The site is down.** Uptime is watched from outside AutoGMap, by the
  team's Grafana (point it at https://indev.eko.in/autogmap/health: healthy
  is HTTP 200 with `"status":"healthy"`). On the server: `docker compose ps`,
  `docker compose logs backend --since 15m`.
- **An agent or an automatic action misbehaves.** Agent quality → Controls
  (admin): every one has its own switch, and it stops at once. Besides the
  template agents and the bot's FAQ answers: **Campaign sending** (running
  campaigns stop before their next batch; Resume picks them up later), the
  bot's reminders, follow-ups, the auto-reply greeting, the Gujarat
  investment video, and DigiLocker. The scraping autopilot has its own switch
  on the Dashboard.
- **The bot misbehaves.** Inbox → Bot settings: switch the bot off. Questions
  then go to the team.
- **A bad campaign.** Campaign History → the campaign → Cancel. Campaigns of
  200+ people already wait for a second person's approval.
- **A deploy broke something.** `bash scripts/rollback.sh` (section 3).
- **Who did what.** Agent quality → Audit log (admin and managers).

## 6. Security

What the app does on its own:

- **Sign-in attempts.** Five wrong passwords for one address in 15 minutes
  lock it for 15 minutes; 20 from one network address lock that. The same
  answer either way, so it reveals no accounts. Every sign-in, failed and
  locked ones too, is in the audit log.
- **Sessions** are signed with `AUTH_JWT_SECRET` (set it in `.env`, 32+
  characters: `openssl rand -hex 32`). Without it, a random key is made once
  in `data/.auth_jwt_secret`; never the database password.
- **The password reset code** works for 10 minutes and 5 tries.
- **Browser protections** on every answer: no sniffing, no framing, a strict
  referrer.
- **`.env`** is made readable by its owner only on every deploy.

What has to be done by hand:

- **The deploy SSH key.** An SSH key made for an assistant to deploy
  (`autogmap-deploy`, ED25519, `SHA256:qQup6L5aIVoZrc17sMiRXGzjy0XsX/jKok3IIRQhykI`)
  is no longer used: deploys are done by hand. Remove it from the server's
  `authorized_keys` (the line ending in `autogmap-deploy`), then delete
  `~/.ssh/r730` and `~/.ssh/r730.pub` on the laptop.
- **Deploying as root.** Every step here runs as root. Running them as the
  `mansi` user needs that user in the `docker` group, which the server's
  administrator decides (the docker group is root-equivalent anyway, so the
  gain is mostly an audit trail of who ran what).
- **The repository is public.** Anyone can read the code, `CLAUDE.md` and how
  the bot and agents work; no keys are in it (`.env` is ignored). Making it
  private (GitHub → Settings → Danger zone → Change visibility) hides that;
  CI then counts against GitHub's 2,000 free Actions minutes a month for a
  private repository (about 10 minutes a push).

## 7. Owners

- Production, deploys and the admin role: Mansi Kanchan.
- Second approver for large campaigns: Kavya Shukla (manager), or another
  operator or manager.
