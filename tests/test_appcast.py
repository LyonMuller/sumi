from pathlib import Path
import unittest
import xml.etree.ElementTree as ElementTree

from sumi import __version__
from tools.make_appcast import appcast, changelog_section, markdown_to_html

ROOT = Path(__file__).resolve().parents[1]
SPARKLE = '{http://www.andymatuschak.org/xml-namespaces/sparkle}'
SIGNATURE = 'sparkle:edSignature="abc+/=" length="1234"'


class AppcastTests(unittest.TestCase):
    def test_current_version_has_changelog_notes(self):
        notes = changelog_section((ROOT / 'CHANGELOG.md').read_text(), __version__)
        self.assertTrue(notes)
        self.assertNotIn('## ', notes)

    def test_section_stops_at_next_version(self):
        text = '# H\n\n## 1.1.0 — novo\n\n- a\n\n## 1.0.0 — velho\n\n- b\n'
        self.assertEqual(changelog_section(text, '1.1.0'), '- a')
        with self.assertRaises(ValueError):
            changelog_section(text, '2.0.0')

    def test_markdown_subset(self):
        result = markdown_to_html('Intro <x>.\n\n- **Um.** com `code`\n  e continuação.\n- [link](https://a.b)')
        self.assertEqual(result, '<p>Intro &lt;x&gt;.</p>\n<ul><li><b>Um.</b> com <code>code</code> '
                                 'e continuação.</li><li><a href="https://a.b">link</a></li></ul>')

    def test_appcast_is_valid_sparkle_feed(self):
        feed = appcast('9.9.9', 'https://x/Sumi-9.9.9.zip', SIGNATURE, '<p>ok ]]> fim</p>',
                       'Tue, 27 Oct 2026 12:00:00 GMT')
        item = ElementTree.fromstring(feed).find('channel/item')
        self.assertEqual(item.findtext(f'{SPARKLE}version'), '9.9.9')
        self.assertEqual(item.findtext(f'{SPARKLE}minimumSystemVersion'), '15.0')
        self.assertEqual(item.findtext('description'), '<p>ok ]]> fim</p>')
        enclosure = item.find('enclosure')
        self.assertEqual(enclosure.get('url'), 'https://x/Sumi-9.9.9.zip')
        self.assertEqual(enclosure.get(f'{SPARKLE}edSignature'), 'abc+/=')
        self.assertEqual(enclosure.get('length'), '1234')

    def test_rejects_unexpected_signature(self):
        with self.assertRaises(ValueError):
            appcast('1.0.0', 'https://x', 'garbage', '', 'date')


if __name__ == '__main__':
    unittest.main()
