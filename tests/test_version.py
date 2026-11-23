"""Versioning and README link hygiene tests for qmap-ai-toolkit.

Run from the repository root:
    python3 -m unittest discover -s tests
"""
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SEMVER_RE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
HARDCODED_VER_RE = re.compile(r'\bv\d+(?:\.\d+)*\b', re.IGNORECASE)


class TestVersioning(unittest.TestCase):
    def test_version_file_is_valid_semver(self):
        version_path = REPO_ROOT / 'VERSION'
        self.assertTrue(version_path.is_file(), 'Missing root VERSION file')
        raw = version_path.read_text(encoding='utf-8')
        self.assertTrue(raw.endswith('\n'), 'VERSION should end with a newline')
        version = raw.strip()
        self.assertRegex(version, SEMVER_RE, f'VERSION is not MAJOR.MINOR.PATCH SemVer: {version!r}')
        major = int(version.split('.')[0])
        self.assertGreaterEqual(major, 4, 'SemVer releases start at 4.0.0')

    def test_changes_top_heading_matches_version(self):
        version = (REPO_ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        first_line = (REPO_ROOT / 'CHANGES.md').read_text(encoding='utf-8').splitlines()[0]
        self.assertTrue(
            first_line.startswith(f'# v{version} ') or first_line == f'# v{version}',
            f'CHANGES.md first heading {first_line!r} does not match VERSION {version!r}',
        )

    def test_doc_titles_and_template_banners_do_not_hardcode_versions(self):
        title_files = [
            REPO_ROOT / 'README.md',
            REPO_ROOT / 'GUIDE.md',
            REPO_ROOT / 'qmap' / 'ITEMS.md',
        ]
        for path in title_files:
            first_line = path.read_text(encoding='utf-8').splitlines()[0]
            self.assertIsNone(
                HARDCODED_VER_RE.search(first_line),
                f'{path.relative_to(REPO_ROOT)} title hardcodes a version: {first_line!r}',
            )

        template_files = [
            REPO_ROOT / 'template' / '_core.py',
            REPO_ROOT / 'template' / '_out.py',
            REPO_ROOT / 'template' / 'plan.py',
            REPO_ROOT / 'template' / 'texgen_blockout.py',
            REPO_ROOT / 'template' / 'views.py',
        ]
        for path in template_files:
            banner = '\n'.join(path.read_text(encoding='utf-8').splitlines()[:3])
            self.assertIsNone(
                HARDCODED_VER_RE.search(banner),
                f'{path.relative_to(REPO_ROOT)} banner hardcodes a version: {banner!r}',
            )
            self.assertNotIn(
                'qmap-toolkit',
                banner,
                f'{path.relative_to(REPO_ROOT)} banner uses old name qmap-toolkit instead of qmap-ai-toolkit',
            )


class TestReadmeLinks(unittest.TestCase):
    def test_readme_references_guide_up_front(self):
        lines = (REPO_ROOT / 'README.md').read_text(encoding='utf-8').splitlines()
        head = '\n'.join(lines[:15])
        self.assertIn('GUIDE.md', head, 'README.md should reference GUIDE.md up front')

    def test_readme_local_links_and_images_exist(self):
        text = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
        # Match markdown links/images ](target) and HTML href="target" / src="target"
        targets = re.findall(r'\]\(([^)\s]+)\)', text)
        targets += re.findall(r'(?:href|src)="([^"]+)"', text)
        self.assertTrue(targets, 'Expected links/images in README.md')
        slug_cache = {}
        for target in targets:
            if target.startswith(('http://', 'https://', 'mailto:', '#')):
                continue
            rel_path, _, anchor = target.partition('#')
            resolved = REPO_ROOT / rel_path
            self.assertTrue(
                resolved.exists(),
                f'Broken relative target in README.md: {target!r} -> {resolved}',
            )
            if anchor and resolved.suffix.lower() == '.md':
                if resolved not in slug_cache:
                    md = resolved.read_text(encoding='utf-8')
                    slug_cache[resolved] = {
                        re.sub(r'\s+', '-', re.sub(r'[^\w\s-]', '', m.group(1).strip().lower()))
                        for m in re.finditer(r'^#{1,6}\s+(.+)$', md, re.M)
                    }
                self.assertIn(
                    anchor,
                    slug_cache[resolved],
                    f'Broken markdown anchor in README.md: {target!r}',
                )


if __name__ == '__main__':
    unittest.main()
