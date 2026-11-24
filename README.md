# Wegard CMMS Client releases

Signed releases of the Wegard CMMS tablet Client. Each release `client-r<N>` carries two assets: `client-<N>.zip`, the package, and `client-<N>.zip.sig`, its SSH signature. `verify_release.py` in this repo checks the signature and prints what the package is, and `wegard-cmms-client.service` is the Client's systemd unit, the same on every tablet. This page is the tablet team's procedure for fetching, verifying, inspecting, trying and installing a release on a tablet, switching releases and replacing the tablet's token.

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

The status shows `active (running)` and `enabled`, the next line `User=wegard-cmms` and `UMask=0077`, and the journal since the start has no traceback. The service sends a heartbeat at start: since then telemetry shows no `sending_stopped` or `worker_failed` line and no `heartbeat_failed` without a later `heartbeat_failed_recovered` (a successful heartbeat writes no line of its own), and `heartbeatsSent` in `usage.json` counts it (on a handed-over tablet, it is above the count noted earlier). A service that stops with exit code 2 is not restarted: its journal says why the token or options were refused.

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

When the backend refuses the tablet's token with `401`, because the token was revoked or replaced, the Client stops sending for good: no reports and no heartbeats. The service stays `active (running)` and keeps picking up new requests, which wait until it is restarted with a valid token. A restart with the old token stops again at its first send. Check for a stop:

```sh
sudo grep sending_stopped /var/lib/wegard-cmms/telemetry.jsonl
sudo journalctl -u wegard-cmms-client --no-pager | grep sending_stopped
sudo ls -A /var/lib/wegard-cmms/pending /home/configs/outbox
```

A stop shows a telemetry line with `"event":"sending_stopped"` and `"status":401`, and a journal line `sending_stopped (report 401 <error>)` or `sending_stopped (heartbeat 401 <error>)`. The last command lists the requests held since: they are sent after the restart. Never delete them or anything else in `pending/` or the Outbox.

For a planned token change, follow the same steps without waiting for a stop.

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

Wait a minute, then run step 6's check block. The `sending_stopped` line from before the restart may still show in the telemetry tail; only one dated after the restart means the new token was refused too. Then check that the held requests were sent:

```sh
sudo ls -A /var/lib/wegard-cmms/pending /home/configs/outbox
```

`pending/` is empty and the Outbox holds nothing but `failed`, if that exists. A request still listed may be waiting for the link; run the command again a few minutes later.
