# Wegard CMMS Client releases

Signed releases of the Wegard CMMS tablet Client. Each release `client-r<N>` carries two assets: `client-<N>.zip`, the package, and `client-<N>.zip.sig`, its SSH signature. `verify_release.py` in this repo checks the signature and prints what the package is, and `wegard-cmms-client.service` is the Client's systemd unit, the same on every tablet. This page is the tablet team's procedure for fetching, verifying, inspecting, trying and installing a release on a tablet.

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

Compare both SHA-256 sums with the ones your team received at handoff. If either differs, stop.

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

This makes the verified release the tablet's boot service `wegard-cmms-client`. It runs as the system account `wegard-cmms` from `/opt/wegard-cmms/current`, reads its token from `/var/lib/wegard-cmms/token`, keeps its state and telemetry in `/var/lib/wegard-cmms` and reads the Tablet Interface's files in `/home/configs`. Run every block in the step 2 directory, in the same shell, so `N` is still set. Each block stops at the first failure; if one fails, stop.

If a Client already runs on this tablet, stop it and keep it from starting at boot, for example `sudo systemctl disable --now wegard-cmms-client`. Its state is handed over below.

Create the account:

```sh
getent passwd wegard-cmms ||
  sudo useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin wegard-cmms
```

Install the release and make it current:

```sh
sudo mkdir -p /opt/wegard-cmms/releases &&
  sudo mkdir /opt/wegard-cmms/releases/$N &&
  sudo unzip -q client-$N.zip -d /opt/wegard-cmms/releases/$N &&
  sudo ln -sfn releases/$N /opt/wegard-cmms/current &&
  ls -l /opt/wegard-cmms/current
```

If `mkdir` fails because `releases/$N` exists, stop: an installed release is never overwritten. The last line shows `current -> releases/<N>`.

Set the tablet's values: `API_URL` is the backend URL your team received at handoff, `IFACE` the modem's network interface (`ip -br link` lists it; on the test tablet it is `wwu1u1i4`). For example `API_URL=https://cmms.example.com IFACE=wwu1u1i4`. Then write them where the service reads them:

```sh
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
  sudo -u wegard-cmms sh -c 'umask 077 && cat > /var/lib/wegard-cmms/token'
  ```

- **A Client ran here before**, stopped above, with its token at `/var/lib/wegard-cmms/token` and its state in `/var/lib/wegard-cmms`. Hand them over in place:

  ```sh
  sudo chown -R wegard-cmms:wegard-cmms /var/lib/wegard-cmms &&
    { [ ! -d /home/configs/outbox/failed ] || sudo chown wegard-cmms:wegard-cmms /home/configs/outbox/failed; } &&
    sudo ls -lA /var/lib/wegard-cmms
  ```

  Every entry is owned by `wegard-cmms`. If its token or state lived elsewhere, stop and ask.

Install and start the service:

```sh
sudo install -m 644 wegard-cmms-client.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now wegard-cmms-client
```

Check it:

```sh
systemctl status wegard-cmms-client --no-pager
sudo journalctl -u wegard-cmms-client -b --no-pager
sudo tail -n 5 /var/lib/wegard-cmms/telemetry.jsonl
sudo cat /var/lib/wegard-cmms/usage.json
```

The status shows `active (running)` and `enabled`, and the journal has no traceback. The service sends a heartbeat at start: telemetry shows no `heartbeat_failed`, `sending_stopped` or `worker_failed` line since then (a successful heartbeat writes no line of its own), and `heartbeatsSent` in `usage.json` counts it. A service that stops with exit code 2 is not restarted: its journal says why the token or options were refused.
