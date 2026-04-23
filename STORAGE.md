# STORAGE — Lotus Lane

Durability map per [empire storage doctrine](../.claude/projects/C--Users-rahul/memory/feedback_storage_doctrine.md): rows→Supabase, code→Git, blobs→GCS.

## Sources of truth

| Asset | Store | Path / location |
|---|---|---|
| Strip metadata (29+ published) | Git | `strips.json` |
| Pipeline code, templates | Git | `pipeline/`, `emails/`, `ikeda/` |
| Wisdom Library (Ikeda quotes, 315) | Git | `ikeda/quotes.json` |
| Strip PNG images (~440MB) | Git (separate repo) + GCS mirror | `~/lotus-lane-assets` → GitHub Pages CDN; mirrored to `gs://lotus-lane-content/assets_mirror/` |
| Daily quote card PNGs | **GCS** | `gs://lotus-lane-content/cards/` |
| Hook reel MP4s (15-sec, costs API $ to regenerate) | **GCS** | `gs://lotus-lane-content/reels/` |
| Per-strip scripts + panel PNGs (the "negatives" — can't be regenerated with same content) | **GCS** | `gs://lotus-lane-content/strips_cache/` |
| Daimoku Daily subscribers | Supabase | `daimoku_subscribers` |
| Email log (sends + challenges) | Supabase | `daimoku_email_log` |
| New-strip notification list | Supabase | `content_subscribers` |
| Published videos (secondary) | YouTube | channel uploads |
| Sent email archive (secondary) | Resend | regeneratable from Supabase + code |

## GCS bucket

- **Name:** `gs://lotus-lane-content`
- **Project:** `astromedha-cron` (shared empire GCP project for content backups)
- **Region:** `asia-south1`
- **Versioning:** on
- **Lifecycle:** Standard → Archive at 90 days; noncurrent versions deleted at 365 days
- **Access:** uniform bucket-level; public access prevented
- **Initial upload:** 2026-04-23 (post content-durability audit)

## Pipeline rule

`generate-strip.yml` and related workflows must sync new outputs to GCS immediately after generation. Local `cards/`, `reels/`, and `strips/cache/` are gitignored and must stay that way — they are caches, not sources of truth.

To sync on demand from a generation machine:
```
gcloud storage rsync --recursive cards gs://lotus-lane-content/cards
gcloud storage rsync --recursive reels gs://lotus-lane-content/reels
gcloud storage rsync --recursive strips/cache gs://lotus-lane-content/strips_cache
```

To restore on a new machine:
```
gcloud storage rsync --recursive gs://lotus-lane-content/cards cards
gcloud storage rsync --recursive gs://lotus-lane-content/reels reels
gcloud storage rsync --recursive gs://lotus-lane-content/strips_cache strips/cache
```

Per CI gotcha #12 in CLAUDE.md: if a video pipeline run fails mid-step, the cache dies with the runner and the video cannot be re-rendered with identical content. The GCS mirror of `strips/cache/` is the insurance against that.

## Asset repo

`lotus-lane-assets` (served by GitHub Pages CDN) is the primary store for published strip PNGs. A belt-and-suspenders copy lives at `gs://lotus-lane-content/assets_mirror/` — protects against GitHub account lockout / takedown / accidental force-push. Migrate the CDN off GitHub before the asset repo crosses 10GB.
