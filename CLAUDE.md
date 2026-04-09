# CLAUDE.md — The Lotus Lane

## What This Is
Nichiren Buddhism-inspired 4-panel comic strip series. Auto-generates strips (Claude for scripts, GPT-4o for images), renders via Playwright, creates YouTube Shorts, hosts on GitHub Pages. Includes "Daimoku Daily" email subscriber system, "Gosho Decoder" sub-product, and "Ikeda Guidance" quote library.

## Pipeline Flow
```
Mon/Wed/Fri 11:30 AM IST → generate-strip.yml
  1. Claude Sonnet → 4-panel script (JSON)
  2. GPT-4o (gpt-image-1) → 4 panel images (1024x1024)
  3. QC pass (gpt-4o-mini vision) → retry bad panels (max 3x)
  4. Playwright → dialogue bands + footer → final strip PNG
  5. Push PNG to assets CDN repo → commit SEO page + sitemap to main
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
| `pipeline/generate_ikeda_pages.py` | Ikeda Guidance — generates SEO pages from quotes library |
| `ikeda/quotes.json` | 315 curated Ikeda quotes across 21 themes |
| `ikeda/index.html` | Ikeda Guidance landing page (search + browse by theme) |
| `ikeda/{theme}.html` | Individual theme pages (courage, hope, peace, etc.) |

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

## Session — Apr 8, 2026

### Features Shipped
- **Ikeda Guidance Library**: 315 quotes across 21 themes (courage, hope, human revolution, prayer, youth, dialogue, peace, education, victory, compassion, wisdom, friendship, perseverance, happiness, action, women, health, life & death, gratitude, kosen-rufu, mentor-disciple)
- **Ikeda SEO Pages**: 22 HTML pages with Schema.org, OG tags, WhatsApp share buttons
- **Strip Engine**: Now uses both Nichiren AND Ikeda quotes in comic strips
- **Daimoku Daily KB**: 315 Ikeda quotes added to email knowledge base
- **WhatsApp Quote Card Generator** (`pipeline/generate_quote_card.py`): 1080x1080 Pillow-generated "Good Morning" cards, rotates themes, tracks history
- **Daimoku Daily Welcome Sequence**: 3-email automated sequence (zero Claude API cost), challenge-to-theme mapping, runs before regular emails
- **Google Search Console**: Verified on both `thelotuslane.in` and `zombielabsv2.github.io/lotus-lane/`, sitemap submitted (106 URLs)
- **Custom Domain DNS**: `thelotuslane.in` A records now point directly to GitHub Pages (was AWS redirect). HTTPS enforced.
- **nav.js**: Added Ikeda Guidance to site-wide top nav + bottom tab bar
- **YouTube retry fix**: `youtube_upload.py` was missing `sys.path.insert` — `from pipeline.utils` failed in CI

### Gotchas
- **nav.js is the single source of truth for navigation** — never add static `<nav>` elements to HTML pages. nav.js dynamically injects top bar + bottom tab bar on all pages.
- **SITE_URL must match the Search Console verified property** — sitemap URLs pointing to a different domain than the verified property causes "couldn't fetch"
- **GoDaddy domain forwarding locks A records** — must delete forwarding rule before you can edit DNS records
- **GitHub Pages subdirectory paths**: from `ikeda/theme.html`, use `../` (one level up) not `../../` to reach site root

### Growth Roadmap (#13-#22)
| # | Priority | Feature |
|---|----------|---------|
| #13 | P0 | Google Search Console — DONE |
| #14 | P0 | WhatsApp Good Morning cards — generator built, needs daily cron |
| #15 | P1 | Pinterest distribution — needs credentials |
| #16 | P1 | Reddit r/GetMotivated — manual posting |
| #17 | P1 | Welcome email sequence — DONE |
| #18 | P1 | TikTok cross-posting — manual initially |
| #19 | P2 | Creative Commons licensing |
| #20 | P2 | Community story submissions |
| #21 | P2 | Listicle-format comics |
| #22 | P3 | Hindi bilingual content |

## Session — Apr 10, 2026

### Image CDN Migration
- **Strip PNGs moved to separate repo**: `zombielabsv2/lotus-lane-assets` (public, GitHub Pages)
- **CDN URL**: `https://zombielabsv2.github.io/lotus-lane-assets/{date}.png`
- **Config**: `ASSETS_BASE_URL` in `pipeline/config.py` — single source of truth for CDN base
- **Workflow**: `generate-strip.yml` pushes PNGs to assets repo via GH_PAT before committing metadata to main
- **strips.json**: `image` field now contains absolute CDN URLs (not relative paths)
- **notify.py**: uses `STRIPS_DIR / f"{strip['date']}.png"` for local path (not strip["image"] which is now a URL)
- **verify_integrity.py**: updated to handle CDN URLs (skips local file check for http:// images)
- **strips/*.png** in `.gitignore` — PNGs still generated locally during CI for video/email, just not committed

### Gotchas
- **PNGs still exist locally** in `strips/` (gitignored). Pipeline generates them for video_generator and notify email attachment. They're just not tracked in git.
- **Legacy PNGs in git history** still bloat `.git/` (~636MB). Can be cleaned with `git filter-repo` later if needed — requires force push.
- **GitHub Pages build takes 1-2 min** for the assets repo. New strip images have a brief delay before CDN serves them.
