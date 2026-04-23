# STORAGE — Lotus Lane

Durability map per [empire storage doctrine](../.claude/projects/C--Users-rahul/memory/feedback_storage_doctrine.md): rows→Supabase, code→Git, blobs→GCS.

## Sources of truth

| Asset | Store | Path / location |
|---|---|---|
| Strip metadata (29+ published) | Git | `strips.json` |
| Pipeline code, templates | Git | `pipeline/`, `emails/`, `ikeda/` |
| Wisdom Library (Ikeda quotes, 315) | Git | `ikeda/quotes.json` |
| Strip PNG images (~440MB) | Git (separate repo) | `~/lotus-lane-assets` → GitHub Pages CDN |
| Daimoku Daily subscribers | Supabase | `daimoku_subscribers` |
| Email log (sends + challenges) | Supabase | `daimoku_email_log` |
| New-strip notification list | Supabase | `content_subscribers` |
| Published videos (secondary) | YouTube | channel uploads |
| Sent email archive (secondary) | Resend | regeneratable from Supabase + code |

## Local-only gaps (to migrate)

These are currently gitignored and live only on the generation machine. They will move to GCS `gs://lotus-lane-content` as the pipeline matures:

- `cards/` — daily quote card PNGs
- `reels/{date}.mp4` — 15-sec hook reels (costs API $ to regenerate)
- `strips/cache/{date}/` — per-workflow scratch, safe to be ephemeral

## Asset repo caveat

`lotus-lane-assets` abuses GitHub as a CDN. Fine at current scale (~440MB); migrate to `gs://lotus-lane-content` when the asset repo crosses ~5GB or before it crosses 10GB. Per doctrine: do not abuse Git as a CDN for large binaries.

## Blobs (planned)

Create `gs://lotus-lane-content` when migrating `cards/`, `reels/`, and the asset repo. Same config as `gs://moonpath-content` (asia-south1, versioning, lifecycle to Archive at 90d).
