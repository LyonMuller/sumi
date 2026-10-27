#!/usr/bin/env python3
"""Writes the Sparkle appcast for one macOS release.

    tools/make_appcast.py --version 0.7.0 --archive macos/dist/Sumi-0.7.0.zip \
        --signature 'sparkle:edSignature="..." length="123"' --output macos/dist/appcast.xml

The appcast lists only the newest version: it is uploaded with each GitHub release and the app
reads it from releases/latest/download/appcast.xml. The release notes shown by Sparkle come from
the version's section in CHANGELOG.md.
"""
from __future__ import annotations

import argparse
import html
import re
from email.utils import formatdate
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'https://github.com/LyonMuller/sumi'
MINIMUM_MACOS = '15.0'


def changelog_section(text: str, version: str) -> str:
    """Body of the '## <version> — title' section, without its heading."""
    match = re.search(rf'^## {re.escape(version)}\b.*?$\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match:
        raise ValueError(f'CHANGELOG.md não tem a seção {version}')
    return match.group(1).strip()


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)


def markdown_to_html(text: str) -> str:
    """The small Markdown subset used in CHANGELOG.md: paragraphs and '- ' lists, bold, code, links."""
    blocks: list[str] = []
    items: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(f'<p>{inline(" ".join(paragraph))}</p>')
            paragraph.clear()
        if items:
            blocks.append('<ul>' + ''.join(f'<li>{inline(item)}</li>' for item in items) + '</ul>')
            items.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith('- '):
            if paragraph:
                flush()
            items.append(stripped[2:])
        elif items and line.startswith('  '):
            items[-1] += ' ' + stripped
        else:
            paragraph.append(stripped)
    flush()
    return '\n'.join(blocks)


def appcast(version: str, url: str, signature: str, notes: str, date: str) -> str:
    if not re.fullmatch(r'sparkle:edSignature="[^"]+" length="\d+"', signature.strip()):
        raise ValueError(f'assinatura inesperada do sign_update: {signature!r}')
    notes = notes.replace(']]>', ']]]]><![CDATA[>')
    return f'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Sumi</title>
    <link>{REPOSITORY}</link>
    <language>pt-BR</language>
    <item>
      <title>Sumi {version}</title>
      <pubDate>{date}</pubDate>
      <sparkle:version>{version}</sparkle:version>
      <sparkle:shortVersionString>{version}</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>{MINIMUM_MACOS}</sparkle:minimumSystemVersion>
      <sparkle:fullReleaseNotesLink>{REPOSITORY}/releases/tag/v{version}</sparkle:fullReleaseNotesLink>
      <description><![CDATA[{notes}]]></description>
      <enclosure url="{html.escape(url)}" type="application/octet-stream" {signature.strip()}/>
    </item>
  </channel>
</rss>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--signature', required=True, help='saída do sign_update')
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    url = f'{REPOSITORY}/releases/download/v{arguments.version}/{arguments.archive.name}'
    notes = markdown_to_html(changelog_section((ROOT / 'CHANGELOG.md').read_text(), arguments.version))
    arguments.output.write_text(appcast(arguments.version, url, arguments.signature, notes,
                                        formatdate(usegmt=True)))
    print(arguments.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
