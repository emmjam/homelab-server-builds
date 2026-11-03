#!/usr/bin/env python3
"""Build a reproducible VSIX from an explicit runtime allowlist; no credentials/deps."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1] / 'RufusVSCode'
FILES = ['package.json', 'extension.js', 'client.js', 'README.md',
         'media/index.html', 'media/panel.js', 'media/panel.css']


def package(output):
    metadata = json.loads((ROOT / 'package.json').read_text())
    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
<Metadata><Identity Language="en-US" Id="{escape(metadata['name'])}" Version="{escape(metadata['version'])}" Publisher="{escape(metadata['publisher'])}"/><DisplayName>{escape(metadata['displayName'])}</DisplayName><Description xml:space="preserve">{escape(metadata['description'])}</Description><Tags>rufus,chat</Tags><Categories>Other</Categories><GalleryFlags>Public</GalleryFlags><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(metadata['engines']['vscode'])}"/><Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value=""/><Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value=""/></Properties></Metadata>
<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/>
<Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/><Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/></Assets></PackageManifest>'''
    types = '''<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="html" ContentType="text/html"/><Default Extension="css" ContentType="text/css"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>'''
    entries = {'extension.vsixmanifest': manifest.encode(), '[Content_Types].xml': types.encode()}
    entries.update({'extension/' + name: (ROOT / name).read_bytes() for name in FILES})
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    print(json.dumps({'package': str(output), 'sha256': hashlib.sha256(Path(output).read_bytes()).hexdigest(), 'files': len(entries)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    package(parser.parse_args().output)
