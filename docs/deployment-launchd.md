# macOS launchd Deployment

The current deployment model is local macOS automation with `launchd`.

## Concept

Each report has:

- A script under `work/<report>/`.
- A `.env` file with credentials and runtime configuration.
- A wrapper script that loads env, checks network, then runs Python.
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

## Template Files

- `deploy/launchd/daily-report.plist.example` for fixed daily schedules.
- `deploy/launchd/interval-report.plist.example` for interval jobs such as
  polling or snapshot collection.
- `deploy/launchd/run_report.sh.example` for loading env and running a report.

Copy these templates to your runtime directory, replace placeholders, and make
the wrapper executable.

## Install Example

```bash
APP_DIR="$HOME/Library/Application Support/DailyBriefingBot/cctv_daily"
mkdir -p "$APP_DIR" "$HOME/Library/LaunchAgents"

cp deploy/launchd/run_report.sh.example "$APP_DIR/run_report.sh"
chmod +x "$APP_DIR/run_report.sh"

sed \
  -e "s#__LABEL__#com.example.cctv-daily#g" \
  -e "s#__APP_DIR__#$APP_DIR#g" \
  -e "s#__HOUR__#8#g" \
  -e "s#__MINUTE__#0#g" \
  deploy/launchd/daily-report.plist.example \
  > "$HOME/Library/LaunchAgents/com.example.cctv-daily.plist"

launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.example.cctv-daily.plist"
launchctl enable gui/$(id -u)/com.example.cctv-daily
```

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
