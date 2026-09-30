# Automatic profile activity

The README embeds an SVG from the `codex-stats` branch. An hourly desktop
automation runs `scripts/update_codex_stats.py --publish` on Chase's Mac.
No separate server, OpenAI API billing, or GitHub Actions secret is required.

The updater retrieves `/backend-api/wham/profiles/me` from `chatgpt.com`, the
same internal endpoint used by the installed ChatGPT desktop profile page.
This is an undocumented integration and can change. Retrieval errors preserve
the last published image; its timestamp remains visible.

Only headline metrics, daily token totals, reasoning
and fast-mode percentages, skill totals, and top skill/plugin names and counts
are published. Conversation text, account/workspace IDs, internal skill/plugin
IDs, display names, usernames, profile photo URLs, email addresses, and credentials are excluded.

The existing access token is read from `~/.codex/auth.json` and sent only to
the fixed OpenAI HTTPS endpoint, with certificate verification enabled and redirects
disabled. The updater does not refresh or modify login credentials. Open the
desktop app and sign in again if authentication stops working. GitHub writes
use the existing local `gh` login.

Run a refresh manually:

```sh
python3 scripts/update_codex_stats.py --publish
```

Render a local preview without publishing:

```sh
python3 scripts/update_codex_stats.py
```

The preview is written to `/private/tmp/codex-profile-preview`. Public output
is committed atomically to the `codex-stats` branch as
`assets/codex-activity-v2.svg` and `assets/codex-stats.json`. The default branch
is untouched by routine refreshes. Unchanged data produces no commit, except
for the daily date rollover needed to advance the calendar. Streaks and totals
come directly from the service; heatmap colors use quartiles of active days
in the displayed year. GitHub's image cache may delay visible changes.

Pause or delete the **GitHub profile stats** automation in the desktop app
to stop automatic updates. It requires the Mac and desktop app to be running
and network access to be available.

Layout revisions use a new image filename so an earlier cached layout does not
remain visible after the README changes.
