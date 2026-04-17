# Video Pipeline Brittleness Report
**Date:** 2026-04-17
**Scope:** Why 18 of 35 comic strips are missing their YouTube upload, and what in the pipeline made it easy to get here without anyone noticing.

## 1. The damage

| Bucket | Count | Dates | State | Recoverable? |
|---|---|---|---|---|
| A — MP4 exists locally, never uploaded | 13 | 2026-01-05, 01-07, 02-09..02-27, 03-02..03-06 | In `shorts/`, no `youtube_id` | Yes, after cutoff removed + OAuth refreshed |
| B1 — Uploaded to YouTube, tracking lost | 2 | 2026-04-06, 2026-04-13 | Live on YouTube (`AZ_En0KETE8`, `isJ6vjUDBkk`), not in `strips.json` | Yes — restored this session |
| B2 — Video generated in CI, deleted before commit, never re-uploaded | 2 | 2026-04-15, 2026-04-17 | No MP4, no YouTube video | **No** without re-running Claude+GPT (different content) |
| C — Pre-video-pipeline orphan | 1 | 2026-01-09 | No cache, no MP4 | No |

Total: **18 strips** (≈51% of the catalog) without a working YouTube video.

## 2. How each bucket happened

### Bucket A — The 30-day cutoff blackhole
- `pipeline/youtube_upload.py` grew a `--all` code path on 2026-04-05 (`commit 017cb49d — "Skip videos older than 30 days in YouTube retry workflow"`).
- The cutoff was added to avoid re-uploading ancient content after a refactor, but there was no corresponding "drain the backlog first, then enable the cutoff" step.
- `retry-uploads.yml` runs `--all` daily. Every day it silently skipped the 13 old strips. They were invisible in logs (no "skipped" counter), invisible in outcomes (step reported success), and invisible in strips.json (no flag that said "this was skipped because it's too old").
- There was no durable record of "did we intentionally leave these behind, or did we forget?" — only a line of code.

### Bucket B1 — The self-destructive commit step (lost tracking)
- 2026-04-06 and 2026-04-13 were uploaded to YouTube successfully. The CI logs show `[date] Uploaded! https://youtube.com/shorts/<id>` for both.
- `save_youtube_id()` wrote the ID back into `strips.json`.
- The next workflow step (`Commit video and social media IDs`) ran:
  ```bash
  git checkout -- . 2>/dev/null || true   # ← reverted the strips.json edit
  git clean -fd 2>/dev/null || true       # ← deleted shorts/*.mp4 (untracked)
  git pull --rebase || true
  git add strips.json shorts/              # ← nothing to stage; already wiped
  ```
- These two lines were added on 2026-04-11 in `commit 862817d — "harden all workflows: clean unstaged files before git pull --rebase"` to fix an Apr 6 incident where `git pull --rebase` failed on unstaged changes.
- The "fix" was correct in isolation (yes, it makes `pull --rebase` succeed), but broken in the full context of the workflow: the unstaged changes were *the outputs the step was about to commit*.
- This kind of bug can't be caught by unit tests — it only manifests when a full pipeline run produces outputs across multiple steps.

### Bucket B2 — Same self-destruct + OAuth refresh failure
- 2026-04-15 and 2026-04-17: the `save_youtube_id()` path never ran because `get_access_token()` hit a `400 Bad Request` on `https://oauth2.googleapis.com/token`. This is consistent with `invalid_grant` — the `YOUTUBE_REFRESH_TOKEN` has been revoked or its OAuth consent expired.
- Even if the OAuth had worked, the same `git clean -fd` would have deleted the MP4. So these strips have no recoverable video at all.

### Bucket C — Pre-video-era orphan
- 2026-01-09 predates the video pipeline. No cache, no MP4 ever existed. Nothing to recover without re-generating the entire strip.

## 3. Why none of this turned the dashboard red

This is the core structural problem.

Every optional step in `generate-strip.yml` had `continue-on-error: true`:
- Video generation → silent pass even when nothing was saved
- YouTube upload → silent pass on upload crash
- Commit video/IDs → silent pass even when the commit was a no-op after self-destruct

The only place failures surfaced was the `Report failure summary` step at the end, which *did* send failure emails. But:
- The run itself was marked **success** on GitHub's Actions dashboard (because `continue-on-error` promotes the step outcome to pass).
- Failure emails piled up and got filed as noise.
- `c04913c` on Apr 15 ("stop failure email spam") made `pull_view_counts` best-effort — a rational response to email noise, but it reduced the signal further.

Result: a pipeline that visually reported success for 4 consecutive runs while destroying its own output.

## 4. The systemic pattern (not specific to YouTube)

Recurring mechanism in this repo:
1. A step in the pipeline encounters a transient or edge-case failure.
2. A commit adds `continue-on-error: true` *or* a defensive cleanup (`git checkout -- .`, `git clean -fd`) to "harden" against that failure.
3. The hardening works for the originally-observed failure mode.
4. The hardening silently disables detection of a *different*, adjacent failure mode.
5. That new failure mode silently compounds across multiple runs before a human notices symptoms (in this case, missing videos on published strips).
6. A new session diagnoses the compounded damage, writes a fix, occasionally introduces step (2) again.

Evidence in git log (last 14 days, YouTube-related commits only):
- 2026-04-05: Add failure alert email → Fix retry catch per-video errors → Skip videos older than 30 days (the cutoff)
- 2026-04-06: Fix YouTube upload quota handling → Restore YouTube IDs + add swap-old workflow → Fix swap order
- 2026-04-07: Fix clear error on missing OAuth client config → Fix reorder pipeline
- 2026-04-08: Fix YouTube retry crash — ModuleNotFoundError → Fix deprecated Claude model + retry workflow fault isolation
- 2026-04-10: Fix 4 YouTube IDs lost in failed push race (Apr 8)
- 2026-04-11: **harden all workflows: clean unstaged files before git pull --rebase** ← this session's root cause
- 2026-04-12: Fix video generator handles 3-panel strips
- 2026-04-15: Fix retry-uploads — make pull_view_counts best-effort, stop failure email spam

Eight consecutive days of fix-on-fix commits on the same pipeline. Each individual fix was reasonable. The cumulative effect was to optimize for "pipeline appears green" at the cost of "pipeline actually works."

## 5. Structural fixes applied this session

1. **Removed `git checkout -- .` and `git clean -fd` from both commit steps in `generate-strip.yml`.** Replaced with `git pull --rebase --autostash origin main`, which handles stray unstaged files without destroying them.
2. **Removed `continue-on-error: true` from `commit_social` step.** If we can't commit the youtube_id after uploading, the run should turn red. The upstream `video` and `youtube` steps keep `continue-on-error` — their failures are non-critical for core publishing and the failure reporter catches them.
3. **Removed the 30-day cutoff in `youtube_upload.py --all`.** Iterates newest-first now; backlog drains over subsequent daily runs (5/day under the YouTube quota).
4. **Added response-body logging in `get_access_token()`.** Next OAuth 400 will surface `invalid_grant` vs other error codes directly in the CI log.
5. **Restored orphan youtube_ids** for 04-06 and 04-13 into `strips.json`, regenerated SEO pages so "Watch on YouTube" embeds are live.
6. **Added gotchas #10–#12 to CLAUDE.md** covering the anti-patterns, so future sessions encounter the warning before re-digging the landmine.

## 6. What's still required (and cannot be done autonomously)

- **Re-authorize YouTube OAuth.** The `YOUTUBE_REFRESH_TOKEN` GitHub secret is returning `400 Bad Request`. This requires:
  1. Running `python pipeline/youtube_upload.py --auth` locally (opens browser for Google consent)
  2. Updating the `YOUTUBE_REFRESH_TOKEN` secret in GitHub → Settings → Secrets → Actions
  
  Until this is done, no new uploads can happen, and the Bucket A backlog cannot drain.

- **04-15 and 04-17 videos.** These are unrecoverable without re-running the full Claude+GPT pipeline, which would replace the published strip content with different text/images. Recommend leaving as gaps.

## 7. Process changes to break the fix-on-fix cycle

Not code. Durable habits documented in CLAUDE.md Gotchas #10–#12:

1. **Workflow edits trigger a manual dispatch.** Every change to a `.github/workflows/*.yml` gets tested with `gh workflow run` before the next cron. The Apr 11 bug would have been caught same-day.
2. **`continue-on-error: true` is an opt-in smell, not a default.** It belongs on steps whose failure is acceptable to the pipeline *as a whole*. When a step produces output the next step needs, that step cannot be continue-on-error.
3. **"Hardening" commits need their blast radius documented.** If a fix adds defensive cleanup (clean, checkout, reset), the PR/commit must name the specific failure being defended against and the scope of files affected. "harden all workflows" with no narrower scope is exactly the kind of broad stroke that produced this incident.
4. **A rate of fix-on-fix commits on a single file/subsystem is itself a signal.** Eight days of patches on the YouTube pipeline should have triggered a step back to ask "is this design right?" rather than continuing to patch.

## 8. Recommended decision point

Re-evaluate the video pipeline on 2026-05-17 (60 days of uploads). Criteria to keep investing engineering time:
- Any single video >1,000 views, OR
- Channel total >5,000 views, OR
- ≥50 subscribers

Current state (40 days, 17 tracked uploads): 481 total views, two outlier hits drove 84% of traffic, median 1–4 views per video. Data is weak but not definitive — the 60-day review is the honest cut-off.
