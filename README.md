# Wegard CMMS Client releases

Signed releases of the Wegard CMMS tablet Client. Each release `client-r<N>` carries two assets: `client-<N>.zip`, the package, and `client-<N>.zip.sig`, its SSH signature. `verify_release.py` in this repo checks the signature and prints what the package is. This page is the tablet team's procedure for fetching, verifying, inspecting and trying a release on a tablet. Installing it as the tablet's service comes in a later version of this procedure.

## Requirements

Debian 13 with `curl`, `unzip`, `python3` and `ssh-keygen` (package `openssh-client`). No GitHub account, token or `gh` is needed; everything is downloaded anonymously.

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
  curl -fLO https://raw.githubusercontent.com/wegardtrail/cmms-client-releases/main/verify_release.py
```

The block stops at the first failure. If `mkdir` fails because the directory exists, remove it or pick another name; start from an empty directory. If a download fails, stop.

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

It prints the Client's usage and exits 0. The package is now in `~/client-r$N-check/client-$N/`. Do not point it at the tablet's real `/home/configs` from here; running it as the tablet's service is the later installation step.
