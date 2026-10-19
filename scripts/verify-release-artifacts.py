#!/usr/bin/env python3
"""Check that update metadata describes exactly the release APK being uploaded."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import os

apk = Path('artifacts/Danygramm-arm64.apk')
metadata = json.loads(Path('artifacts/danygramm-update.json').read_text())
sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
badging = subprocess.run([str(sdk / 'build-tools/36.0.0/aapt'), 'dump', 'badging', str(apk)],
                         capture_output=True, text=True, check=True).stdout
match = re.search(r"^package: name='([^']+)' versionCode='([0-9]+)'", badging, re.M)
if not match or match[1] != 'org.miccontrol.messenger.web' or 'application-debuggable' in badging:
    raise SystemExit('Release APK must use the Danygramm package and must not be debuggable.')
expected = {'package': match[1], 'versionCode': int(match[2]), 'apk': apk.name,
            'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(), 'size': apk.stat().st_size}
if metadata != expected or not 0 < apk.stat().st_size <= 160 * 1024 * 1024:
    raise SystemExit('Update metadata does not match the release APK.')
print('Release package, non-debug manifest and update metadata verified.')
