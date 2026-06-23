# macOS launchd Deployment

The current deployment model is local macOS automation with `launchd`.

## Concept

Each report has:

- A script under `work/<report>/`.
- A `.env` file with credentials and runtime configuration.
- A wrapper script that loads env, then runs `python3 -m daily_briefing.cli`.
- A launchd plist generated from `deploy/launchd/*.plist.example`.

For open-source use, always replace labels, script names, and paths with your
own local values before installation.

## Recommended Schedule Pattern

Start each task a few minutes before the desired push time and set
`SEND_AT_LOCAL` to the actual delivery time.

Example:

| Report | launchd start | `SEND_AT_LOCAL` |
| --- | ---: | ---: |
| AI daily | 07:50 | 07:50 |
| WeChat daily | 07:55 | 07:55 |
| CCTV daily | 08:00 | 08:00 |
| Knowledge Planet | 22:05 | 22:05 |

If a report needs expensive precomputation, start launchd earlier and keep
`SEND_AT_LOCAL` as the actual delivery time. If you do not want precomputation,
make the launchd start time and `SEND_AT_LOCAL` identical.

## CLI Install

The recommended path is to let the CLI generate the wrapper and plist:

```bash
python3 -m daily_briefing.cli launchd install cctv \
  --project-dir "$HOME/Developer/daily-briefing-bot" \
  --app-dir "$HOME/Library/Application Support/DailyBriefingBot/cctv_daily" \
  --hour 8 \
  --minute 0 \
  --copy-env
```

Edit the generated `.env`, then load the job:

```bash
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.daily-briefing.cctv.plist"
launchctl enable gui/$(id -u)/com.daily-briefing.cctv
```

You can also pass `--load` to the install command to reload the job immediately.
The generated wrapper sends a primary-robot failure alert when the report command
exits non-zero.

For interval jobs such as hot-search collection:

```bash
python3 -m daily_briefing.cli launchd install weibo \
  --project-dir "$HOME/Developer/daily-briefing-bot" \
  --app-dir "$HOME/Library/Application Support/DailyBriefingBot/weibo_hot" \
  --interval-seconds 1800
```

## Template Files

- `deploy/launchd/daily-report.plist.example` for fixed daily schedules.
- `deploy/launchd/interval-report.plist.example` for interval jobs such as
  polling or snapshot collection.
- `deploy/launchd/run_report.sh.example` for loading env, running a report, and
  sending a failure alert.

The templates remain useful if you need hand-written local customization.

## Disable Example

```bash
launchctl bootout gui/$(id -u) "$HOME/Library/LaunchAgents/com.example.cctv-daily.plist"
launchctl disable gui/$(id -u)/com.example.cctv-daily
```

## Notes

- A sleeping Mac may not run tasks exactly on time.
- Network checks can open a VPN client in the original local setup; this should
  be treated as a local customization, not a default open-source behavior.
- Logs should stay local and ignored by git.
