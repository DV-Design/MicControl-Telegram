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

# Keep the decoded manifest in memory: it contains the runtime Maps API key.
manifest = subprocess.run([str(sdk / 'build-tools/36.0.0/aapt'), 'dump', 'xmltree',
                           str(apk), 'AndroidManifest.xml'],
                          capture_output=True, text=True, check=True).stdout
maps_entries = []
elements = []
metadata_entries = []
current_metadata = None
for line in manifest.splitlines():
    element = re.match(r'^( *)E: ([^\s(]+)', line)
    if element:
        depth, name = len(element[1]), element[2]
        while elements and elements[-1][0] >= depth:
            elements.pop()
        current_metadata = None
        if name == 'meta-data':
            current_metadata = {'parents': tuple(item[1] for item in elements), 'attributes': {}}
            metadata_entries.append(current_metadata)
        elements.append((depth, name))
    elif current_metadata is not None:
        attribute = re.search(r'A: android:(name|value)\([^)]*\)="([^"]*)"', line)
        if attribute:
            current_metadata['attributes'][attribute[1]] = attribute[2]
maps_entries = [entry for entry in metadata_entries if entry['attributes'].get('name') in
                {'com.google.android.geo.API_KEY', 'com.google.android.maps.v2.API_KEY'}]
if (len(maps_entries) != 1 or maps_entries[0]['parents'] != ('manifest', 'application') or
        maps_entries[0]['attributes'].get('name') != 'com.google.android.geo.API_KEY'):
    raise SystemExit('Release APK must contain exactly one com.google.android.geo.API_KEY directly under application.')
maps_key = maps_entries[0]['attributes'].get('value', '')
if not re.fullmatch(r'AIza[A-Za-z0-9_-]{35}', maps_key):
    raise SystemExit('Release APK Maps key is missing or has an invalid format.')
environment_key = os.environ.get('GOOGLE_MAPS_API_KEY', '').strip()
if os.environ.get('CI') == 'true' and not environment_key:
    raise SystemExit('Set GOOGLE_MAPS_API_KEY in CI to verify the packaged Maps key.')
if environment_key and maps_key != environment_key:
    raise SystemExit('Packaged Maps key does not match GOOGLE_MAPS_API_KEY from the environment.')
maps_proof = {'apkSha256': expected['sha256'], 'package': match[1], 'versionCode': int(match[2]),
              'sourceCommit': os.environ.get('GITHUB_SHA') or None,
              'metadataName': 'com.google.android.geo.API_KEY', 'present': True, 'formatValid': True,
              'keySha256': hashlib.sha256(maps_key.encode()).hexdigest(),
              'matchesEnvironment': maps_key == environment_key if environment_key else None,
              'liveMapRenderingValidated': False}
Path('artifacts/maps-configuration.json').write_text(json.dumps(maps_proof, indent=2) + '\n')
print('Release package, non-debug manifest, update metadata and Maps configuration verified.')
