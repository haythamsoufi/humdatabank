"""The template versions admin guide must exist in every UI language and link to real pages."""

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ADMIN_DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'user-guides' / 'admin'
LANGUAGES = ('', '.fr', '.es', '.ar', '.ru')
GUIDES_REFERENCING_IT = (
    'edit-template',
    'form-builder-advanced',
    'troubleshooting-templates-and-assignments',
)


@pytest.mark.parametrize('suffix', LANGUAGES)
def test_guide_exists_and_links_resolve(suffix):
    guide = ADMIN_DOCS / f'template-versions{suffix}.md'
    assert guide.is_file(), f'missing {guide.name}'
    text = guide.read_text(encoding='utf-8')
    assert text.strip()
    for target in re.findall(r'\]\(([^)#]+\.md)\)', text):
        assert (guide.parent / target).resolve().is_file(), f'{guide.name} links to missing {target}'


@pytest.mark.parametrize('suffix', LANGUAGES)
def test_translations_cover_the_same_sections_as_english(suffix):
    english = (ADMIN_DOCS / 'template-versions.md').read_text(encoding='utf-8')
    other = (ADMIN_DOCS / f'template-versions{suffix}.md').read_text(encoding='utf-8')
    count = lambda text, prefix: len(re.findall(rf'^{prefix} ', text, flags=re.M))
    assert count(other, '##') == count(english, '##')
    assert count(other, '###') == count(english, '###')
    assert other.count('\n|---') == english.count('\n|---')


@pytest.mark.parametrize('suffix', LANGUAGES)
@pytest.mark.parametrize('guide', GUIDES_REFERENCING_IT)
def test_related_guides_point_to_it_in_every_language(guide, suffix):
    text = (ADMIN_DOCS / f'{guide}{suffix}.md').read_text(encoding='utf-8')
    assert 'template-versions.md' in text
