#!/usr/bin/env python3
"""Validate release inputs and restore the existing signing key without exposing secrets."""

import base64
import binascii
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


EXPECTED_CERT_SHA256 = "59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe"
PUBLIC_SAMPLE_HASH = "014b35b6184100b085b0d0572f9b5103"


def fail(message):
    sys.exit("::error::" + message)


def main():
    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    maps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    encoded_key = os.environ.get("MICCONTROL_DEBUG_KEYSTORE_B64", "").strip()
    if not api_id or not api_hash:
        fail("Add repository Actions secrets TELEGRAM_API_ID and TELEGRAM_API_HASH from my.telegram.org/apps.")
    if not re.fullmatch(r"[1-9][0-9]{0,8}", api_id) or not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
        fail("Telegram API secrets have an invalid format; use your own api_id and 32-digit hexadecimal api_hash.")
    if api_id == "4" or api_hash.lower() == PUBLIC_SAMPLE_HASH:
        fail("Public upstream sample API credentials are forbidden in CI. Configure your own Telegram API app.")
    if os.environ.get("MICCONTROL_ALLOW_SAMPLE_API", "false").lower() != "false":
        fail("MICCONTROL_ALLOW_SAMPLE_API must remain false in CI.")
    if not maps_key:
        fail("Add repository Actions secret GOOGLE_MAPS_API_KEY for Maps SDK for Android.")
    if not re.fullmatch(r"AIza[A-Za-z0-9_-]{35}", maps_key):
        fail("GOOGLE_MAPS_API_KEY has an invalid format; use a Maps SDK for Android API key.")
    if not encoded_key:
        fail("Repository Actions secret MICCONTROL_DEBUG_KEYSTORE_B64 is missing; preserve the existing signing key.")
    try:
        key_bytes = base64.b64decode("".join(encoded_key.split()), validate=True)
    except (binascii.Error, ValueError):
        fail("MICCONTROL_DEBUG_KEYSTORE_B64 is not valid base64.")
    keytool = shutil.which("keytool")
    if not keytool:
        fail("JDK keytool is required to verify the existing signing identity.")
    with tempfile.TemporaryDirectory(prefix="miccontrol-ci-key-") as directory:
        key_file = Path(directory) / "debug.keystore"
        key_file.write_bytes(key_bytes)
        key_file.chmod(0o600)
        common = ["-keystore", str(key_file), "-storepass", "android", "-alias", "androiddebugkey"]
        try:
            certificate = subprocess.run([keytool, "-exportcert", *common],
                                         capture_output=True, timeout=20, check=True).stdout
            if hashlib.sha256(certificate).hexdigest() != EXPECTED_CERT_SHA256:
                fail("Signing certificate differs from the installed Danygramm APK.")
            subprocess.run([keytool, "-certreq", *common, "-keypass", "android",
                            "-file", str(Path(directory) / "proof.csr")],
                           capture_output=True, timeout=20, check=True)
        except (OSError, subprocess.SubprocessError):
            fail("Signing key is invalid or cannot be opened with the expected debug alias/password.")
        destination = Path(".local/miccontrol-debug.keystore")
        destination.parent.mkdir(mode=0o700, exist_ok=True)
        destination.write_bytes(key_bytes)
        destination.chmod(0o600)
    print("Telegram and Maps input formats and existing private signing key validated; no API request was made.")


if __name__ == "__main__":
    main()
