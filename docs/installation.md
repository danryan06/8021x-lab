# Installation guide

This is a start-to-finish install for a **fresh machine**, written for people who
may be new to Docker, the command line, or 802.1X. If you already have Docker and
Git, you can skip to [Step 3](#step-3-get-the-code).

By the end you'll have the whole lab running: a web UI at `http://localhost:3000`,
an API, a PostgreSQL database, and a live FreeRADIUS server — all in containers.

**New to the terminology?** The [concepts guide](concepts.md) explains what
802.1X, RADIUS, and certificates are and why they matter. You don't need it to
install, but it's a good next read.

---

## Fast path: one-line install (Linux / Raspberry Pi)

On a 64-bit Linux machine (including 64-bit Raspberry Pi OS), one command does
the entire installation below — checks the platform, installs Git/Make/Docker if
missing, downloads the code to `~/8021x-lab`, creates your configuration with a
random `SECRET_KEY`, and starts the lab:

```bash
curl -fsSL https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/install.sh | bash
```

Notes:

- **Prefer to read before you run?** (Good instinct.) Download it first:

```bash
curl -fsSLO https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/install.sh
less install.sh        # read it
bash install.sh        # then run it
```

- It will ask for your **sudo password** to install packages.
- It handles the Docker permission setup for you (no mid-install reboot needed);
  it just reminds you at the end to log out/in once so `docker` works without
  `sudo` in future sessions.
- **Re-running is a clean reinstall.** It pulls the latest code, deletes the
  previous lab database / RADIUS logs / certificates, and starts fresh. Your
  `.env` (admin password, secrets) is kept.
- **To update without wiping data**, use the upgrade script (see
  [Updating to the latest version](#updating-to-the-latest-version)).
- macOS/Windows aren't covered by the script — follow the manual steps below
  with Docker Desktop.

When it finishes, jump to [Step 6: Log in and verify](#step-6-log-in-and-verify).
The rest of this guide is the **manual path** — the same steps, explained one at
a time, worth reading if you want to understand what the installer did.

---

## What you'll need

| Thing | Why | Notes |
|-------|-----|-------|
| A 64-bit computer | Runs the containers | Linux, macOS, Windows, or a Raspberry Pi 4/5 |
| ~4 GB RAM free | Building/running the images | 2 GB works but the first build is slow |
| Internet access | Download images and the code | Only needed for install/build |
| A terminal | Run the commands below | "Terminal" on macOS/Linux, "PowerShell" on Windows |

> **Raspberry Pi users:** use **64-bit Raspberry Pi OS** (or 64-bit Ubuntu). See
> [the Raspberry Pi section](#raspberry-pi-notes) before you start — the rest of
> this guide applies to you too.

The two pieces of software you must install first are **Git** (to download the
code) and **Docker** (to run everything). The next step installs both.

---

## Step 1: Install the prerequisites

A "command" below is a line you type into the terminal and press Enter. Lines
starting with `#` are comments explaining what the next command does — don't type
those.

### Linux (Debian, Ubuntu, or Raspberry Pi OS)

```bash
# 1. Update the list of available software
sudo apt-get update

# 2. Install Git (downloads the project) and make (a convenience command runner)
sudo apt-get install -y git make

# 3. Install Docker + the Compose plugin using Docker's official script
curl -fsSL https://get.docker.com | sudo sh

# 4. Let your user run Docker without typing "sudo" every time
sudo usermod -aG docker "$USER"

# 5. REQUIRED — reboot so step 4 takes effect. Skipping this causes
#    "permission denied ... docker.sock" errors later. (A full log out and
#    log back in also works.)
sudo reboot
```

After the reboot, open a terminal again and continue with
[Verify the prerequisites](#verify-the-prerequisites).

### macOS or Windows

1. Install **Docker Desktop** from <https://www.docker.com/products/docker-desktop/>
   and start it (wait for the whale icon to say "Docker Desktop is running").
2. Install **Git**:
   - macOS: `git` is included with the Xcode command-line tools; if it's missing,
     run `xcode-select --install`, or install [Homebrew](https://brew.sh) and
     `brew install git`.
   - Windows: install [Git for Windows](https://git-scm.com/download/win), which
     also gives you a "Git Bash" terminal you can run the commands in.
3. `make` is optional on these platforms — this guide always shows the plain
   `docker compose` commands as an alternative.

### Verify the prerequisites

Run these; each should print a version number without an error:

```bash
git --version
docker --version
docker compose version
```

If `docker` gives a "permission denied" or "cannot connect to the Docker daemon"
error on Linux, you either didn't log out/in after Step 1.4, or the Docker
service isn't running (`sudo systemctl start docker`). On macOS/Windows, make sure
Docker Desktop is actually running.

---

## Step 2: (understanding what happens next)

You're about to **download the project's code**, **create a configuration file**,
and **start the lab**. Nothing touches the rest of your system — everything runs
inside Docker containers you can stop or delete later
([see uninstalling](#uninstalling-or-resetting)).

---

## Step 3: Get the code

Pick a folder to keep the project in (your home directory is fine), then clone
(download) the repository with Git:

```bash
# Go to your home directory
cd ~

# Download the project — this creates a folder named "8021x-lab"
git clone https://github.com/danryan06/8021x-lab.git

# Move into the project folder — run all later commands from here
cd 8021x-lab
```

> **No Git, or prefer a download?** On the
> [repository page](https://github.com/danryan06/8021x-lab), click the green
> **Code** button → **Download ZIP**, unzip it, and `cd` into the unzipped folder.
> Git is recommended because it makes [updating](#updating-to-the-latest-version)
> a one-line command.

To confirm you're in the right place, `ls` (or `dir` on Windows) should show
files like `docker-compose.yml`, `README.md`, and folders `backend/`, `frontend/`.

---

## Step 4: Create your configuration

The project ships an example configuration you copy into a real one called `.env`.
This file holds settings like the admin password and database credentials.

```bash
cp .env.example .env
```

For a first run on your own machine, the defaults work as-is. **Before showing
the lab to anyone else or putting it on a shared network, open `.env` and change
at least these:**

- `ADMIN_PASSWORD` — the password for the web UI (default `admin`)
- `SECRET_KEY` — used to sign login sessions; set a long random string
- `POSTGRES_PASSWORD` — the database password

Edit it with any text editor, e.g. `nano .env` (save with `Ctrl+O`, exit with
`Ctrl+X`).

---

## Step 5: Start the lab

This one command builds the images, starts every service, sets up the database,
and creates a starter "Default Lab":

```bash
make bootstrap
```

**No `make`?** `./scripts/bootstrap.sh` is the same command. Or start Compose
directly — schema and the Default Lab are created as the backend starts:

```bash
docker compose up -d --build
```

The **first run downloads and builds images and will take a while** — a few
minutes on a laptop, longer on a Raspberry Pi. Later starts are fast. When it
finishes you'll see the UI/API addresses printed.

---

## Step 6: Log in and verify

1. Open a web browser to **<http://localhost:3000>**.
   (If the lab is on another machine — like a Pi — use that machine's IP instead
   of `localhost`, e.g. `http://192.168.1.50:3000`.)
2. Log in with the admin username and password from your `.env`
   (defaults: `admin` / `admin`).
3. On the **Dashboard**, the Database, API, and FreeRADIUS panels should read
   healthy.

Now run a real authentication in under a minute:

- Open **Auth Test**, and follow the
  [first PEAP login walkthrough](usage.md#guide-your-first-peap-login-password-based).
- Or open the **Wizard** for a fully guided path.

If it accepts (or rejects, when you test a wrong password) and a row appears under
**Auth Events**, your installation works end to end.

---

## Raspberry Pi notes

The lab runs well on a Raspberry Pi, with a few specifics:

- **Use a 64-bit OS.** 64-bit Raspberry Pi OS or 64-bit Ubuntu on a Pi 4 or 5.
  The container images are built for 64-bit ARM; a 32-bit OS will fail to install
  some Python components.
- **Give the build headroom.** A Pi with 4 GB+ RAM is comfortable. On a 2 GB Pi
  the initial frontend build is the most likely step to run out of memory; if it
  fails, close other programs and re-run `make bootstrap` (it resumes).
- **A Pi is a great host for testing real switches/APs.** Because it's a real
  Linux host (not Docker Desktop), it preserves the source IP of incoming RADIUS
  requests, so per-device RADIUS clients work correctly. Put the Pi on the same
  network as your switch/AP, point that device's RADIUS settings at the Pi's IP on
  UDP `1812`, and register it under **RADIUS Clients** (see
  [usage.md](usage.md#guide-pointing-a-real-switch-or-access-point-at-the-lab)).
- **Access from another computer.** Browse to `http://<pi-ip>:3000`. Find the
  Pi's IP with `hostname -I`.

---

## Managing the lab

Run these from inside the project folder (`~/8021x-lab`). The `make` form and the
plain `docker compose` form do the same thing.

| Task | With `make` | With `docker compose` |
|------|-------------|-----------------------|
| Start | `make up` | `docker compose up -d` |
| Stop (keeps data) | `make down` | `docker compose down` |
| Upgrade (keep data) | `make upgrade` | `./scripts/upgrade.sh` |
| Clean reinstall (wipe data) | `make reset` then `make up` | `./scripts/reset-lab.sh` then `docker compose up -d --build` |
| View logs | `make logs` | `docker compose logs -f` |
| See service status | `make ps` | `docker compose ps` |

Your data (users, certificates, events, RADIUS logs) lives in Docker volumes and
survives stop/start. The one-line **installer** deletes those volumes on every
re-run so you get a clean lab. The **upgrade** script, `make bootstrap`, and
`make up` do **not** wipe.

---

## Updating to the latest version

On 64-bit Linux (including Raspberry Pi OS), one command pulls the latest code,
rebuilds, and restarts **without** deleting users, events, certificates, or
RADIUS logs:

```bash
curl -fsSL https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/upgrade.sh | bash
```

Prefer to read it first:

```bash
curl -fsSLO https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/upgrade.sh
less upgrade.sh
bash upgrade.sh
```

Already inside the project folder:

```bash
make upgrade
# same as: ./scripts/upgrade.sh
```

Schema updates apply when the backend container starts — you do not run a
separate migrate command. Your `.env` is kept.

macOS/Windows (Docker Desktop), or a manual Git checkout:

```bash
cd ~/8021x-lab
git pull                       # download the latest code
make up                        # rebuild and restart; schema updates apply on backend start
```

Want a **clean lab** instead (empty events, new CA, default users)? Re-run
the [installer](#fast-path-one-line-install-linux--raspberry-pi) — it wipes
data volumes and keeps `.env`.

---

## Troubleshooting

**"permission denied while trying to connect to the docker API at
unix:///var/run/docker.sock" (Linux).** Your user can't talk to Docker yet —
the `docker` group change from Step 1.4 isn't active in this session (most
often: the reboot after `usermod` was skipped). Diagnose:

```bash
groups                 # is "docker" listed for THIS session?
getent group docker    # is your username at the end of this line at all?
```

- Username **is** in `getent group docker` but `groups` doesn't show it →
  your session is stale: `sudo reboot` (or fully log out and back in).
- Username is **not** in `getent group docker` → the usermod never happened:
  `sudo usermod -aG docker "$USER"` then `sudo reboot`.
- Want to continue without rebooting right now? `newgrp docker` activates the
  group in the current shell only.

Verify with `docker ps` (should print an empty table, not an error), then re-run
`make bootstrap` — it's safe to re-run and keeps your detected settings.

**"port is already allocated" / a port is in use.** Something else is using 3000,
8000, 1812, or 1813. Stop that program, or change the published port in
`docker-compose.yml`.

**The first `make bootstrap` seems stuck.** The initial image build is genuinely
slow, especially on a Pi. Watch progress in another terminal with `make logs`.

**The API never became ready / backend logs show schema errors.** The backend
applies the database schema as it starts and retries if Postgres is still coming
up. On a very slow machine, wait and check `docker compose logs backend`.
Re-running `make bootstrap` is safe.

**The UI loads but says it can't reach the API.** Give it a few more seconds after
startup, then refresh; check `make ps` shows all services as `running`/`healthy`.

Still stuck? Grab the logs with `make logs` and open an issue on the
[repository](https://github.com/danryan06/8021x-lab).

---

## Uninstalling or resetting

```bash
# Stop and remove the containers (keeps your data volumes)
make down

# Full reset: delete all data (users, certs, events, RADIUS logs, database)
# The one-line installer does this automatically on every re-run.
# The upgrade script does not.
make reset
# same as: docker compose down -v   (plus leftover volumes from older project names)

# Remove the code entirely
cd ~ && rm -rf 8021x-lab
```

---

## Next steps

- [Concepts](concepts.md) — what 802.1X, RADIUS, and certificates are, and why.
- [Usage guide](usage.md) — step-by-step for every feature.
- [Developer setup](developer-setup.md) — running outside Docker, tests, and CI.
