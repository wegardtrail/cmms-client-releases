# Wegard CMMS Client releases

Signed releases of the Wegard CMMS tablet Client. Each release `client-r<N>` carries two assets: `client-<N>.zip`, the package, and `client-<N>.zip.sig`, its SSH signature. `verify_release.py` in this repo checks the signature and prints what the package is, and `wegard-cmms-client.service` is the Client's systemd unit, the same on every tablet. This page is the tablet team's procedure for fetching, verifying, inspecting, trying and installing a release on a tablet (sections 1 to 6), switching releases (7), replacing the tablet's token (8), maintaining the Composition (9), operating the service (10) and recovering it, including from a wrong clock (11).

## Requirements

Debian 13 with `curl`, `unzip`, `python3`, `ssh-keygen` (package `openssh-client`) and `ca-certificates`. Installing (step 6) needs `sudo`. No GitHub account, token or `gh` is needed; everything is downloaded anonymously.

## 1. Pick the release number

Find the latest release number:

```sh
URL=$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://github.com/wegardtrail/cmms-client-releases/releases/latest) && N=${URL##*/client-r} && echo "$N"
```

It must print a plain number such as `2`. Anything else means stop. To take a specific release instead, set it by hand, for example `N=2`. This lookup only chooses `N`; the signed output in step 3 is what you trust.

## 2. Download into an empty directory

```sh
mkdir ~/client-r$N-check && cd ~/client-r$N-check &&
  curl -fLO https://github.com/wegardtrail/cmms-client-releases/releases/download/client-r$N/client-$N.zip &&
  curl -fLO https://github.com/wegardtrail/cmms-client-releases/releases/download/client-r$N/client-$N.zip.sig &&
  curl -fLO https://raw.githubusercontent.com/wegardtrail/cmms-client-releases/main/verify_release.py &&
  curl -fLO https://raw.githubusercontent.com/wegardtrail/cmms-client-releases/main/wegard-cmms-client.service &&
  sha256sum verify_release.py wegard-cmms-client.service
```

The block stops at the first failure. If `mkdir` fails because the directory exists, remove it or pick another name; start from an empty directory. If a download fails, stop.

Compare both SHA-256 sums with the ones your team received at handoff. If either differs, or you received no sum for one of them, stop and ask.

Write the trusted signing key beside `verify_release.py`:

```sh
cat > allowed_signers <<'EOF'
cmms-release namespaces="client-update" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHy+/czOiy5WiFmhr62EDTd7FH4cPOh8ABt4q97Ms7Bt cmms-release
EOF
```

Compare this line with the copy your team received at handoff. If they differ, stop.

## 3. Verify

```sh
python3 verify_release.py client-$N.zip client-$N.zip.sig; echo "exit $?"
```

The output must be exactly these three lines, with your `N` in the second, followed by `exit 0`:

```text
product wegard-cmms-client
release <N>
runtime debian13-aarch64-python3.13
```

Any other output, a different release number, or a non-zero exit means the package is not genuine or not the one you asked for: do not use it. Verify before you extract anything.

## 4. Inspect

```sh
unzip -l client-$N.zip
```

The listing must contain only `manifest.json` and files under `src/wegard_cmms_agent/`. Anything else, such as a token, key or config file, means stop.

## 5. Extract and try

```sh
unzip -q client-$N.zip -d client-$N &&
  PYTHONPATH=client-$N/src python3 -m wegard_cmms_agent --help
```

It prints the Client's usage and exits 0. The package is now in `~/client-r$N-check/client-$N/`. Do not point it at the tablet's real `/home/configs` from here.

## 6. Install

This makes the verified release the tablet's boot service `wegard-cmms-client`. It runs as the system account `wegard-cmms` from `/opt/wegard-cmms/current`, reads its token from `/var/lib/wegard-cmms/token`, keeps its state and telemetry in `/var/lib/wegard-cmms` and reads the Tablet Interface's files in `/home/configs`. Run every block in the step 2 directory, in the same shell, so `N` is still set. Each block except the final check stops at the first failure; if one fails, stop.

If a Client already runs on this tablet, stop it and keep it from starting at boot, for example `sudo systemctl disable --now wegard-cmms-client`. Its state is handed over below.

Create the account:

```sh
getent passwd wegard-cmms ||
  sudo useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin wegard-cmms
```

Extract the release:

```sh
sudo mkdir -p /opt/wegard-cmms/releases &&
  sudo mkdir /opt/wegard-cmms/releases/$N &&
  sudo unzip -q client-$N.zip -d /opt/wegard-cmms/releases/$N &&
  ls /opt/wegard-cmms/releases
```

If `mkdir` fails because `releases/$N` exists, stop: an installed release is never overwritten. The last line lists your `N` among the installed releases.

Make it current:

```sh
sudo ln -sfn releases/$N /opt/wegard-cmms/current &&
  ls -l /opt/wegard-cmms/current
```

The last line shows `current -> releases/<N>`.

Set the tablet's values: `API_URL` is the backend URL your team received at handoff, `IFACE` the modem's network interface (`ip -br link` lists it; on the test tablet it is `wwu1u1i4`). Set both in this shell on a line of their own, for example `API_URL=https://cmms.example.com IFACE=wwu1u1i4`. Then write them where the service reads them; the block refuses to run while either is empty:

```sh
: "${API_URL:?}" "${IFACE:?}" &&
  sudo mkdir -p /etc/wegard-cmms &&
  printf 'API_URL=%s\nCELLULAR_IFACE=%s\n' "$API_URL" "$IFACE" | sudo tee /etc/wegard-cmms/client.env
```

It prints both lines with your values.

Create the state directory and the Outbox:

```sh
sudo install -d -o wegard-cmms -g wegard-cmms -m 700 /var/lib/wegard-cmms &&
  sudo install -d -o wegard-cmms -g wegard-cmms -m 755 /home/configs/outbox
```

Then do one of the two:

- **New tablet.** Write the token your team received for this tablet. Run the command, paste the token, press Enter, then Ctrl-D:

  ```sh
  sudo -u wegard-cmms sh -c 'umask 077 && cat > /var/lib/wegard-cmms/.token.tmp && mv /var/lib/wegard-cmms/.token.tmp /var/lib/wegard-cmms/token'
  ```

- **A Client ran here before**, stopped above, with its token at `/var/lib/wegard-cmms/token` and its state in `/var/lib/wegard-cmms`. Hand them over in place:

  ```sh
  sudo chown -R wegard-cmms:wegard-cmms /var/lib/wegard-cmms &&
    { [ ! -d /home/configs/outbox/failed ] || sudo chown wegard-cmms:wegard-cmms /home/configs/outbox/failed; } &&
    sudo ls -lA /var/lib/wegard-cmms
  ```

  Every entry is owned by `wegard-cmms`. If its token or state lived elsewhere, stop and ask. Note `heartbeatsSent` from `sudo cat /var/lib/wegard-cmms/usage.json`: the old Client's count carries over.

Write the Composition, `/home/configs/trailers.json`: it names the tablet's Vehicles as the CMMS knows them. The service sends no report and no heartbeat until it has read a valid one. Section 9 describes the format. On a tablet that already has one, show it with `cat /home/configs/trailers.json` and keep it if it lists this tablet's Vehicles. Otherwise run the command, paste the file, press Enter, then Ctrl-D:

```sh
sudo sh -c 't=/home/configs/.trailers.json.tmp && cat > $t && PYTHONPATH=/opt/wegard-cmms/current/src python3 -c "import pathlib, sys; from wegard_cmms_agent.client import load_composition; load_composition(pathlib.Path(sys.argv[1]))" $t && chmod 644 $t && mv $t /home/configs/trailers.json' &&
  ls -l /home/configs/trailers.json
```

The last line shows `-rw-r--r-- 1 root root`. A Python traceback ending in an error such as `ValueError: expected exactly one Anchor vehicle entry` means the pasted file is not valid JSON or breaks a rule of section 9, and `trailers.json` was not changed; fix it and run the command again.

Check that the service account can read the Tablet Interface's files and the Composition, and write in the Outbox:

```sh
for f in log.txt live_ids.json trailers.json; do sudo -u wegard-cmms test -r /home/configs/$f && echo "$f readable"; done
sudo -u wegard-cmms test -r /home/configs/outbox -a -w /home/configs/outbox -a -x /home/configs/outbox && echo "outbox writable"
```

It prints four lines: `log.txt readable`, `live_ids.json readable`, `trailers.json readable` and `outbox writable`. A missing line means the service cannot read that file, or cannot list and delete the requests it has sent. `log.txt` and `live_ids.json` exist only once the Tablet Interface has run; if `ls /home/configs` does not list them, start the Tablet Interface and run the check again. `sudo ls -ld /home/configs /home/configs/*` shows owners and modes: the account needs to read the three files, to enter `/home/configs`, and to read, write and enter `outbox`. Fix the owner or mode, then run the check again. If the Tablet Interface keeps writing a file the account cannot read, stop and ask.

If Tailscale runs on the tablet, turn off its DNS. A name lookup through Tailscale costs 8 to 12 KB over LTE; the tablet's own resolvers answer for under 1 KB. The tablet then no longer resolves tailnet names; SSH to the tablet is unaffected. If you are connected over SSH, keep this session open until the check after it passes:

```sh
if command -v tailscale > /dev/null; then
  sudo tailscale set --accept-dns=false && cat /etc/resolv.conf && sudo tailscale debug prefs | grep CorpDNS
else
  echo "no Tailscale: skip"
fi
```

Without Tailscale it prints `no Tailscale: skip`. Otherwise `resolv.conf` starts with `# Generated by NetworkManager`, lists the connections' resolvers and no `100.100.100.100`, and the last line is `"CorpDNS": false,`. If you are on SSH, check that a new SSH session to the tablet still connects. If that fails, or the check below finds no heartbeat, undo it from the open session with `sudo tailscale set --accept-dns=true`, check access again and ask. `tailscale up --reset` turns Tailscale's DNS back on, so repeat this block after Tailscale is set up again.

Install and start the service:

```sh
T0=$(date '+%F %T') &&
  sudo install -m 644 wegard-cmms-client.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now wegard-cmms-client
```

Wait a minute, then check it:

```sh
systemctl status wegard-cmms-client --no-pager
systemctl show wegard-cmms-client -p User -p UMask
sudo journalctl -u wegard-cmms-client --since "$T0" --no-pager
sudo tail -n 5 /var/lib/wegard-cmms/telemetry.jsonl
sudo cat /var/lib/wegard-cmms/usage.json
```

The status shows `active (running)` and `enabled`, the next line `User=wegard-cmms` and `UMask=0077`, and the journal since the start has no traceback and no `composition_invalid` line (section 9). The service sends a heartbeat at start: since then telemetry shows no `sending_stopped` or `worker_failed` line and no `heartbeat_failed` without a later `heartbeat_failed_recovered` (a successful heartbeat writes no line of its own), and `heartbeatsSent` in `usage.json` counts it (on a handed-over tablet, it is above the count noted earlier). A service that stops with exit code 2 is not restarted: its journal says why the token or options were refused.

## 7. Switch releases

Every installed release stays in `/opt/wegard-cmms/releases/<N>`, and `current` points at the one the service runs. The token, `client.env`, state, telemetry and the Outbox live outside the release directories, so a switch keeps them: requests queued while the service is stopped are picked up after the start, and an interrupted upload is completed by the release that runs next. `current` changes only while the service is stopped. See what is installed and which release runs:

```sh
ls /opt/wegard-cmms/releases; readlink /opt/wegard-cmms/current
```

**Add a newer release.** Do steps 1 to 5 for the new `N` in a fresh directory, then from step 6 run only "Extract the release", in the step 2 directory. The service keeps running the release it ran; `current` does not change.

**Switch.** Note `heartbeatsSent` from `sudo cat /var/lib/wegard-cmms/usage.json`; after the switch, step 6's check expects a higher count. Set `N` to the release to run, on a line of its own, for example `N=3`. Then:

```sh
: "${N:?}" && [ -d /opt/wegard-cmms/releases/$N ] &&
  sudo systemctl stop wegard-cmms-client &&
  sudo ln -sfn releases/$N /opt/wegard-cmms/current &&
  T0=$(date '+%F %T') &&
  sudo systemctl start wegard-cmms-client &&
  ls -l /opt/wegard-cmms/current
```

The last line shows `current -> releases/<N>`. If it prints nothing, or only an error naming `N`, release `N` is not set or not installed and the service was left running; check `N`. Wait a minute, then run step 6's check block. If the check fails, switch back.

**Switch back.** Run the switch block with `N` set to the kept release, for example `N=2`, then step 6's check block. Keep the previous release installed: never delete or overwrite a directory under `releases/`.

## 8. Replace the token

When the backend refuses the tablet's token with `401`, because the token was revoked or replaced, the Client stops sending: no reports and no heartbeats. The service stays `active (running)` and keeps picking up new requests, which wait until it is restarted with a valid token. A restart with the old token stops again at its first send. Suspect a stop when the CMMS shows the tablet's Vehicle presence going stale, or its reports no longer arrive while the tablet is online. Check for a stop:

```sh
sudo grep -a sending_stopped /var/lib/wegard-cmms/telemetry.jsonl
sudo journalctl -u wegard-cmms-client --no-pager | grep sending_stopped
sudo ls -A /var/lib/wegard-cmms/pending /home/configs/outbox
```

A stop shows a telemetry line with `"event":"sending_stopped"` and `"status":401`, and a journal line `sending_stopped (report 401 <error>)` or `sending_stopped (heartbeat 401 <error>)`. Only a line dated after the service's last start, which `systemctl show -p ActiveEnterTimestamp wegard-cmms-client` prints, is a current stop; an older one was ended by a restart. The last command lists the requests held since, apart from the Outbox's `failed` directory: they are sent after the restart. Never delete them or anything else in `pending/` or the Outbox.

For a planned token change, skip this check and follow the rest. A `sending_stopped` line between the team issuing the new token and the restart is expected.

Note `heartbeatsSent` from `sudo cat /var/lib/wegard-cmms/usage.json`; it does not grow while sending is stopped, and step 6's check expects a higher count after the restart.

Write the new token your team received for this tablet. Run the command, paste the token, press Enter, then Ctrl-D:

```sh
sudo -u wegard-cmms sh -c 'umask 077 && cat > /var/lib/wegard-cmms/.token.tmp && mv /var/lib/wegard-cmms/.token.tmp /var/lib/wegard-cmms/token'
```

Restart the service:

```sh
T0=$(date '+%F %T') &&
  sudo systemctl restart wegard-cmms-client
```

Wait a minute, then run step 6's check block in the same shell, so `T0` is still set. The `sending_stopped` line from before the restart may still show in the telemetry tail; only one dated after the restart means the new token was refused too, and a service stopped with exit code 2 refused the token file. Either way, get the correct token from your team, write it with the command above and restart again; leave `pending/` and the Outbox alone. Then check that the held requests were sent:

```sh
sudo ls -A /var/lib/wegard-cmms/pending /home/configs/outbox
```

`pending/` is empty and the Outbox holds nothing but `failed`, if that exists. A request still listed may be waiting for the link; run the command again a few minutes later. A held request the backend refused is not sent but moved to `failed` under the same name; `sudo ls -A /home/configs/outbox/failed` shows whether any request listed before the restart is there.

## 9. Maintain the Composition

The Composition, `/home/configs/trailers.json`, maps each trail ID the tablet hears to the Vehicle's name in the CMMS. It is maintained by hand: update it whenever maintenance changes which Vehicles are coupled, or a technician changes a trail ID in the Tablet Interface's service tab (the Tablet Interface logs the slot, old ID and new ID). The Tablet Interface never writes it. Example:

```json
{ "vehicles": [
    { "trailId": 4, "displayName": "VH-001", "anchor": true },
    { "trailId": 12, "displayName": "VH-008" },
    { "trailId": 17, "displayName": "VH-014" } ] }
```

- Exactly one entry has `"anchor": true`: the Anchor vehicle, which the tablet cannot detect by itself. `anchor` is optional on the others; any value other than `true` or `false` makes the file invalid.
- `trailId` is a whole number from 1 to 65535, each listed once.
- The file is one JSON object with a `vehicles` list.
- `displayName` equals the Vehicle's name in the CMMS exactly; it is not blank and at most 100 characters.
- A report for a trail ID not in the file is filed against the Anchor vehicle, and a live trail ID not in the file is left out of the heartbeat. Telemetry records both (`unknown_trail_id`, `trail_id_unmapped`).

Replace the file whole, while the service runs; never edit it in place, so the service never reads half a file. Run the command, paste the new file, press Enter, then Ctrl-D:

```sh
T0=$(date '+%F %T') &&
  sudo sh -c 't=/home/configs/.trailers.json.tmp && cat > $t && PYTHONPATH=/opt/wegard-cmms/current/src python3 -c "import pathlib, sys; from wegard_cmms_agent.client import load_composition; load_composition(pathlib.Path(sys.argv[1]))" $t && chmod 644 $t && mv $t /home/configs/trailers.json' &&
  ls -l /home/configs/trailers.json
```

The last line shows `-rw-r--r-- 1 root root`. A Python traceback ending in an error such as `ValueError: expected exactly one Anchor vehicle entry` means the pasted file is not valid JSON or breaks a rule of section 9, and `trailers.json` was not changed; fix it and run the command again. No restart is needed: the service reads the file again each time it uses it. Wait a minute, then check it was accepted. The service logs each problem once, when it starts, and again with `_recovered` when it ends, so this shows the last line of each:

```sh
for e in composition_invalid trail_id_unmapped name_rejected; do sudo grep -a "\"event\":\"$e" /var/lib/wegard-cmms/telemetry.jsonl | tail -n 1; done
```

Each line it prints ends a problem (its event ends in `_recovered`), or it prints nothing. A last `composition_invalid` line without `_recovered` means the file is `missing`, `unreadable` (wrong mode) or `invalid`: the service keeps using the last valid version until it restarts, and after a restart with no valid file it sends nothing, so fix the file and replace it again. The new names reach the CMMS with the next heartbeat, within 10 minutes, and its Vehicle presence then shows them online. Run the check again after that heartbeat: a last `trail_id_unmapped` line names a live trail ID the file lacks, and a last `name_rejected` line a `displayName` the CMMS does not know; correct the file and replace it again.

## 10. Operate

Where everything lives:

| Path | Owner, mode | What |
|------|-------------|------|
| `/opt/wegard-cmms/releases/<N>/` | `root` | Installed releases; never changed or deleted |
| `/opt/wegard-cmms/current` | `root` | Link to the release the service runs |
| `/etc/wegard-cmms/client.env` | `root`, `644` | `API_URL` and `CELLULAR_IFACE` |
| `/etc/systemd/system/wegard-cmms-client.service` | `root`, `644` | The service unit |
| `/var/lib/wegard-cmms/` | `wegard-cmms`, `700` | State, kept across releases and reboots |
| `/var/lib/wegard-cmms/token` | `wegard-cmms`, `600` | The tablet's token |
| `/var/lib/wegard-cmms/pending/` | `wegard-cmms` | Requests being sent; never delete |
| `/var/lib/wegard-cmms/telemetry.jsonl` | `wegard-cmms` | One JSON line per event; never rotated by the service |
| `/var/lib/wegard-cmms/usage.json` | `wegard-cmms` | Today's heartbeat count and cellular bytes |
| `/home/configs/trailers.json` | `root`, `644` | The Composition (section 9) |
| `/home/configs/log.txt`, `live_ids.json` | `root` | Written by the Tablet Interface, read by the service |
| `/home/configs/outbox/` | `wegard-cmms`, `755` | Report requests from the Tablet Interface; never delete |
| `/home/configs/outbox/failed/` | `wegard-cmms` | Requests the service could not read or the CMMS refused |

Check the service:

```sh
systemctl status wegard-cmms-client --no-pager
readlink /opt/wegard-cmms/current
sudo journalctl -u wegard-cmms-client --since today --no-pager | tail -n 20
sudo tail -n 5 /var/lib/wegard-cmms/telemetry.jsonl
sudo cat /var/lib/wegard-cmms/usage.json; date +%F
sudo ls -A /var/lib/wegard-cmms/pending /home/configs/outbox
```

A healthy service shows `active (running)` and `enabled`, the release you installed, and no traceback in the journal. A heartbeat goes out every 10 minutes while the tablet has a link, and `heartbeatsSent` in `usage.json` counts them; its `day` equals the date on the next line. `pending/` and the Outbox are empty or hold only requests waiting for the link, apart from `failed`. Telemetry lines start with a timestamp and an `event`; a successful heartbeat or report writes none. Most problems open with one event and close with the same name plus `_recovered`:

- `heartbeat_failed`: heartbeats fail, usually for lack of a link; its `error` names the cause.
- `live_ids_stale`: the Tablet Interface's `live_ids.json` is missing or old, so heartbeats name only the Anchor vehicle.
- `composition_invalid`, `trail_id_unmapped`, `name_rejected`, `unknown_trail_id`: see section 9.
- `request_failed`: a request moved to `failed`.
- `sending_stopped`: the token was refused; see section 8.
- `worker_failed`: the service hit an error and restarts; see section 11.

The service's first sample on a new day writes a `daily_summary` line for the day before, with `heartbeatsSent`, `heartbeatsFailed` and the cellular bytes.

**Stop and start.** Stopping lets the service finish its current step, for up to a minute. Requests the Tablet Interface writes meanwhile wait in the Outbox and are sent after the start:

```sh
sudo systemctl stop wegard-cmms-client && systemctl is-active wegard-cmms-client
```

It prints `inactive`. A stopped service still starts at the next boot; to keep it off across reboots use `sudo systemctl disable --now wegard-cmms-client` instead. To start it again:

```sh
T0=$(date '+%F %T') &&
  sudo systemctl enable --now wegard-cmms-client
```

Wait a minute, then run step 6's check block.

**The `failed` directory.** A request the service could not read, or the CMMS refused for good, moves to `/home/configs/outbox/failed/` under its own name, beside a `.error` file with the reason. It is never sent again. List them and read a reason:

```sh
sudo ls -l /home/configs/outbox/failed
sudo cat /home/configs/outbox/failed/<name>.json.error
```

The service never deletes them. Leave them in place and report them to your team with their reasons.

## 11. Recover

Find out what state the service is in:

```sh
systemctl show wegard-cmms-client -p ActiveState -p ExecMainStatus -p UnitFileState
sudo journalctl -u wegard-cmms-client -n 30 --no-pager
```

A healthy service shows `ActiveState=active` and `UnitFileState=enabled`. Then match the case below.

**Exit code 2.** `ActiveState=failed` and `ExecMainStatus=2`: the service refused its token or options and is not restarted. The journal says which:

- `token file is not a private regular file owned by this user`: fix the owner and mode with `sudo chown wegard-cmms:wegard-cmms /var/lib/wegard-cmms/token && sudo chmod 600 /var/lib/wegard-cmms/token`.
- `cannot read token file`, or `token file is empty or malformed`: write the token your team received for this tablet again. Run the command, paste the token, press Enter, then Ctrl-D:

  ```sh
  sudo -u wegard-cmms sh -c 'umask 077 && cat > /var/lib/wegard-cmms/.token.tmp && mv /var/lib/wegard-cmms/.token.tmp /var/lib/wegard-cmms/token'
  ```

- A line starting `usage:` or naming `--api-url`: `/etc/wegard-cmms/client.env` is wrong. `cat /etc/wegard-cmms/client.env` shows it (`CELLULAR_IFACE` is step 6's `IFACE`). Set `API_URL` and `IFACE` in this shell as step 6 says, then run its block that writes them.

Then start it:

```sh
T0=$(date '+%F %T') &&
  sudo systemctl restart wegard-cmms-client
```

Wait a minute, then run step 6's check block.

**A stopped service.** `ActiveState=inactive`: someone stopped it. Start it as in section 10 (`sudo systemctl enable --now wegard-cmms-client`, then step 6's check block). `UnitFileState=disabled` alone means it will not start at the next boot; the same command fixes that.

**A service that keeps restarting.** The journal shows a traceback every few seconds, or telemetry shows `worker_failed`: the service restarts by itself after 5 s, and work queued in `pending/` and the Outbox is kept. If it does not settle within a few minutes, switch back to the previous release as in section 7 and report the journal lines to your team. `systemctl show` then shows `ActiveState=activating` between tries.

**Anything else.** Any other state that is not `active`: read the journal, switch back to the previous release as in section 7, and report the journal lines to your team.

**A wrong clock.** A clock that is wrong when the service starts shows in two ways: the CMMS rejects the connection as insecure (telemetry `heartbeat_failed` with `"error":"SSLCertVerificationError"`; only the first failure of a run is logged, so check the clock whenever heartbeats fail), or `day` in `usage.json` lies after today's real date, and the service then keeps counting into that day until real time reaches it. Check the clock:

```sh
timedatectl
sudo cat /var/lib/wegard-cmms/usage.json
```

`Universal time` must match the real time within seconds, with `System clock synchronized: yes`, and `day` in `usage.json` is today or earlier. If the clock is wrong, give the tablet a link and set it from the network, then check again:

```sh
sudo chronyc makestep && sleep 10 && timedatectl
```

`makestep` only works once chrony has heard a time server; if the time is still wrong, wait a few minutes and run it again. With the clock right, if `day` in `usage.json` is after today, remove the file while the service is stopped, so it starts a fresh count; that day's counts so far are lost, and nothing else is:

```sh
sudo systemctl stop wegard-cmms-client &&
  sudo rm -f /var/lib/wegard-cmms/usage.json &&
  T0=$(date '+%F %T') &&
  sudo systemctl start wegard-cmms-client
```

Otherwise restart the service so it starts with the right time:

```sh
T0=$(date '+%F %T') &&
  sudo systemctl restart wegard-cmms-client
```

Wait a minute, then run step 6's check block. After removing `usage.json`, `heartbeatsSent` counts only from this start. Remove nothing else in `/var/lib/wegard-cmms`.
