# Onshape Progressor

Watch your robot come together. Onshape Progressor takes a picture of your team's
Onshape part studio or assembly every hour, and saves it only when the CAD actually
changed — building up a timelapse of your whole season. It runs entirely inside
**your own** private copy of this repository on GitHub, for free.

> 🎬 _Your timelapse will appear under [`timelapse/`](timelapse/) after the first
> Timelapse run. Drop a link to your favorite one here._

## Why you can trust it

This repository is **public code with no server behind it**. There is nothing to
sign up for and nobody to trust:

- You make your **own private copy** of this template. Your copy is yours alone.
- Your Onshape API keys are stored as **encrypted GitHub Actions secrets in your
  repo** — never printed in logs, never committed, never sent anywhere but Onshape.
- The rendered images are committed to **your private repo**, nowhere else.

Because the code is public, you (or a mentor) can read every line and confirm it
only ever talks to `cad.onshape.com`. The author never sees your keys, your repo, or
your images.

## Tracked CAD

This section updates itself each time frames are captured — one link per tracked
document, pointing at its folder of frames.

<!-- targets:start -->
_No frames captured yet. Run the Capture workflow to populate this._
<!-- targets:end -->

## Setup (about 10 minutes)

### 1. Make your own copy

Click **“Use this template” → “Create a new repository.”** Choose your team's
account, give it a name, and **set it to Private**. (Use the template button, not
Fork — forks can't be made private and stay linked to this repo.)

### 2. Get your Onshape API keys

1. Go to <https://cad.onshape.com/user/developer/apiKeys/createApiKey>.
2. Tick **“Application can read your documents”** — that's the only permission this
   tool needs; it never modifies your CAD.
3. Click **Create API key**, then copy the **Access key** and **Secret key**
   somewhere safe for the next step. The secret key is shown only once.

> Some Onshape Education plans restrict API keys. If the portal won't let you make a
> key, check with your Onshape account admin that your plan allows API access.

### 3. Add the keys to your repo as secrets

In **your** new repo: **Settings → Secrets and variables → Actions → New repository
secret.** Add two secrets, named exactly:

| Secret name           | Value                       |
| --------------------- | --------------------------- |
| `ONSHAPE_ACCESS_KEY`  | your Onshape **access** key |
| `ONSHAPE_SECRET_KEY`  | your Onshape **secret** key |

### 4. Point it at your CAD

Open your part studio or assembly in Onshape and **copy the URL straight from your
browser's address bar.** It looks like:

```
https://cad.onshape.com/documents/abc123…/w/def456…/e/ghi789…
```

Edit [`config.toml`](config.toml) in your repo (click the file, then the pencil
icon) and paste your URL into the `url` line:

```toml
[[targets]]
url = "https://cad.onshape.com/documents/abc123…/w/def456…/e/ghi789…"
```

That's the only required edit — the document, workspace, and element are all read
from that link, and the name and type are looked up automatically. To track more
than one document, add another `[[targets]]` block with its own `url`. You can also
adjust image size, view angle, and frame rate in the `[settings]` section; each
option is explained inline in the file.

### 5. Turn on Actions

Open the **Actions** tab in your repo and click the green button to enable
workflows. From now on the **Capture** job runs every hour on its own.

> **Start early.** This tool records history *going forward* from the moment you
> turn it on — it does not (and cannot, affordably) reconstruct the past, because
> Onshape's history is one entry per edit and there's no cheap way to replay it.
> Switch Capture on at kickoff and your whole season builds itself. Want a head
> start before adoption? Make a few **Versions** in Onshape at your milestones —
> those are your permanent snapshots regardless of this tool.

### 6. Make the video

**Actions → Timelapse → Run workflow** stitches your frames into an `.mp4` (tick
`gif` for an animated GIF too). It also runs automatically whenever new frames are
captured. The result lands in `timelapse/`, and the **Tracked CAD** section above
links to each document's frames.

## Troubleshooting

- **Capture stopped running after a couple of months.** GitHub disables scheduled
  workflows after 60 days with no repo activity. During build season the hourly
  commits keep it alive; in the offseason it can pause. Leave `keepalive = true` in
  `config.toml` (the default) and it commits a tiny no-op monthly to stay enabled —
  or just open **Actions** in January and re-enable it.
- **Occasional “429” messages.** That's Onshape's per-minute rate limit. The tool
  pauses and retries automatically — nothing to do.
- **“annual API-call quota … is used up (HTTP 402).”** Separate from 429, Onshape
  caps how many API calls an account may make per *year*. The hourly Capture job is
  light (~24–48 calls/day per tracked document), so this is unlikely from normal
  use, but if you share the key with other API tools you could hit it. It resets
  annually, and more calls can be requested from Onshape (api-support@onshape.com).
- **“Onshape rejected the API credentials.”** Double-check the two secret names are
  exactly `ONSHAPE_ACCESS_KEY` / `ONSHAPE_SECRET_KEY`, that you pasted the keys
  without extra spaces, and that the key's owner can open the document in Onshape.
- **“…is not a recognizable Onshape link.”** Copy the URL while viewing the document
  in your **workspace** (the link should contain `/w/`), not a fixed version
  (`/v/`).

## Development

The tool is plain Python (3.11+) with one runtime dependency (`requests`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .          # install the package
pip install pytest ruff   # dev tools

pytest                    # run the test suite (no network needed)
ruff check . && ruff format --check .

# Try a capture locally without writing anything (needs the two env vars set):
ONSHAPE_ACCESS_KEY=… ONSHAPE_SECRET_KEY=… python -m progressor.capture --dry-run

# The timelapse step needs ffmpeg on your PATH (preinstalled on GitHub runners):
#   macOS: brew install ffmpeg   ·   Ubuntu: sudo apt install ffmpeg
```

`--at <ISO-8601>` on the capture job captures a specific past hour, handy for
filling a gap by hand.
