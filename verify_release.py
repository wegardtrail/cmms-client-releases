"""Verify a signed Client release package.

Usage: python3 verify_release.py client-<N>.zip client-<N>.zip.sig

Checks the SSHSIG signature against allowed_signers beside this script, then prints the
manifest's product, release and runtime. Exits non-zero, printing nothing on stdout, on any
failure. Needs only python3 and ssh-keygen; extracts nothing.
"""

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ALLOWED_SIGNERS = Path(__file__).resolve().with_name("allowed_signers")
FIELDS = ("product", "release", "runtime")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    package = Path(argv[1]).read_bytes()
    check = subprocess.run(
        [
            *("ssh-keygen", "-Y", "verify", "-f", str(ALLOWED_SIGNERS)),
            *("-I", "cmms-release", "-n", "client-update", "-s", argv[2]),
        ],
        input=package,
        capture_output=True,
    )
    if check.returncode != 0:
        sys.stderr.buffer.write(check.stdout + check.stderr)
        print("signature rejected", file=sys.stderr)
        return 1
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    if not isinstance(manifest, dict) or any(field not in manifest for field in FIELDS):
        print(f"manifest.json lacks {', '.join(FIELDS)}", file=sys.stderr)
        return 1
    for field in FIELDS:
        print(f"{field} {manifest[field]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
