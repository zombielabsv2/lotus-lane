# CLAUDE.md — The Lotus Lane

## What This Is
Nichiren Buddhism-inspired 4-panel comic strip series. Auto-generates strips (Claude for scripts, GPT-4o for images), renders via Playwright, creates YouTube Shorts, hosts on GitHub Pages. Includes "Daimoku Daily" email subscriber system and "Gosho Decoder" sub-product.

## Pipeline Flow
```
Mon/Wed/Fri 11:30 AM IST → generate-strip.yml
  1. Claude Sonnet → 4-panel script (JSON)
  2. GPT-4o (gpt-image-1) → 4 panel images (1024x1024)
  3. QC pass (gpt-4o-mini vision) → retry bad panels (max 3x)
  4. Playwright → dialogue bands + footer → final strip PNG
  5. Commit strip + SEO page + sitemap
  6. [optional] Video → YouTube → Pinterest → Tumblr → Instagram → Notifications
```

## Key Files

| File | Purpose |
|------|---------|
| `strips.json` | Single source of truth — all strip metadata, YouTube IDs, social IDs |
| `pipeline/generate_strip.py` | Script + image generation + assembly |
| `pipeline/playwright_renderer.py` | Chromium-based text rendering (dialogue bands, video frames) |
| `pipeline/video_generator.py` | edge-tts audio + Ken Burns + ffmpeg → MP4 Shorts |
| `pipeline/youtube_upload.py` | Upload, swap-old, retry. Max 5/run, quota-aware |
| `pipeline/generate_email.py` | Daimoku Daily — Claude + nichiren-chatbot knowledge base |
| `pipeline/generate_pages.py` | SEO HTML pages per strip |
| `pipeline/verify_integrity.py` | Data integrity checks |
| `pipeline/config.py` | Characters (Arjun/Meera/Sudha/Vikram), topics, art style, dimensions |
| `pipeline/notify.py` | Content subscriber email notifications |
| `pipeline/check_subscribers.py` | New subscriber alerts (every 6h) |
| `pipeline/subscribe_api.py` | Subscriber CRUD + stats (`python pipeline/subscribe_api.py` for stats) |
| `pipeline/pinterest_upload.py` | Pinterest pin upload (built, needs credentials) |
| `pipeline/tumblr_upload.py` | Tumblr post upload (built, needs credentials) |
| `pipeline/instagram_upload.py` | Instagram post/reel upload (built, needs Meta verification) |

## Cron Schedule

| Cron | Time (IST) | Workflow | What |
|------|------------|----------|------|
| Mon/Wed/Fri 6:00 UTC | 11:30 AM | `generate-strip.yml` | Full pipeline: script → images → video → social → notify |
| Daily 2:00 UTC | 7:30 AM | `retry-uploads.yml` | YouTube swap-old + pending uploads (max 5 each) |
| Daily 5:30 UTC | 11:00 AM | `send-emails.yml` | Daimoku Daily to subscribers (needs nichiren-chatbot repo) |
| Every 6h | — | `check-subscribers.yml` | New subscriber alert email |
| On push/PR | — | `tests.yml` | pytest |

## Supabase Schema

- **daimoku_subscribers**: name, email, challenges[], frequency (daily/thrice_weekly/weekly), active, subscribed_at, last_sent_at
- **daimoku_email_log**: subscriber_id, challenge_category, sent_at
- **content_subscribers**: email, active (for new-strip notifications)
- Frontend `subscribe.html` uses anon key; backend uses service key

## GitHub Secrets Required

**Active:** ANTHROPIC_API_KEY, OPENAI_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_KEY, RESEND_API_KEY, NOTIFY_EMAIL, GH_PAT (for nichiren-chatbot checkout)

**Not yet configured:** PINTEREST_ACCESS_TOKEN, PINTEREST_REFRESH_TOKEN, PINTEREST_APP_ID, PINTEREST_APP_SECRET, PINTEREST_BOARD_ID, TUMBLR_ACCESS_TOKEN, TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_BLOG_NAME, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID

## Analytics

- **GoatCounter**: `zombielabs.goatcounter.com` — on all pages (index, strips, decoder, subscribe)
- **Visitor badge**: homepage (visitor-badge.laobi.icu)
- **YouTube**: native YouTube Studio analytics only — no pull-back into strips.json yet

## Gotchas

1. **Title dedup**: Claude prompt includes recent quotes but also recent titles — check if new titles overlap with existing ones
2. **YouTube quota**: ~6 uploads/day. `retry-uploads.yml` caps at 5 swap + 5 upload per run. `uploadLimitExceeded` handled gracefully
3. **Concurrent write risk**: `retry-uploads.yml` and `generate-strip.yml` can both modify `strips.json` and push. The generate workflow does `git pull --rebase` before second commit
4. **Cache directory**: `strips/cache/{date}/` has script.json + panel PNGs. Used for reassembly (`--reassemble`) and video generation
5. **3-panel strips**: Early strips (pre-Feb) may have 3 panels. Video generator handles both 3 and 4
6. **Pillow→Playwright migration**: Text rendering switched from Pillow to Playwright (Apr 2026). Old videos flagged `youtube_needs_reupload: true`
7. **continue-on-error**: All optional steps (video, social, notify) use `continue-on-error: true` — failures are silent unless the report step catches them
8. **nichiren-chatbot dependency**: Daimoku Daily emails require `chunks.json` from sibling repo `zombielabsv2/nichiren-chatbot`
9. **Cost per strip**: ~Rs. 5-7 (Claude ~Rs. 1.1, GPT images ~Rs. 3.6/panel × retries, QC negligible)

## Testing
- `pytest tests/ -v` — video generator tests, Daimoku Daily tests, import tests
- `python pipeline/verify_integrity.py` — data integrity (strips.json ↔ files)
- `python pipeline/youtube_upload.py --pending` — YouTube upload status dashboard
