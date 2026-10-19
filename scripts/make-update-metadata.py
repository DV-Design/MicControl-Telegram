#!/usr/bin/env python3
"""Create the small release asset consumed by the Danygramm updater."""
import hashlib
import json
from pathlib import Path
import re
import sys

apk = Path('artifacts/Danygramm-arm64.apk')
match = re.search(r"^package: name='([^']+)' versionCode='([0-9]+)'", sys.stdin.read(), re.M)
if not match or match[1] != 'org.miccontrol.messenger.web':
    sys.exit('Unexpected APK package; update metadata was not created.')
metadata = {'package': match[1], 'versionCode': int(match[2]), 'apk': apk.name,
            'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(), 'size': apk.stat().st_size}
Path('artifacts/danygramm-update.json').write_text(json.dumps(metadata, indent=2) + '\n')
