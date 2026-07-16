"""Tests for inline translation review routes and authorization."""

import base64
import json
import os
import tempfile

import polib
import pytest

from app.services.translation_review.assignment_service import set_user_translator_languages
from tests.factories import _ensure_permission


@pytest.fixture
def translation_po_dir(app, monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        for lang in ('en', 'fr'):
            lc = os.path.join(tmp, lang, 'LC_MESSAGES')
            os.makedirs(lc, exist_ok=True)
            po = polib.POFile()
            po.append(polib.POEntry(msgid='Dashboard', msgstr='Dashboard' if lang == 'en' else 'Tableau de bord'))
            po.save(os.path.join(lc, 'messages.po'))

        import app.routes.admin.utilities.helpers as helpers_module
        import app.routes.admin.utilities.translations as translations_module

        monkeypatch.setattr(
            helpers_module,
            '_translations_po_path',
            lambda locale: os.path.join(tmp, locale, 'LC_MESSAGES', 'messages.po'),
        )
        monkeypatch.setattr(
            translations_module,
            '_translations_po_path',
            lambda locale: os.path.join(tmp, locale, 'LC_MESSAGES', 'messages.po'),
        )
        app.config['SUPPORTED_LANGUAGES'] = ['en', 'fr']
        app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
        yield tmp


@pytest.fixture
def translator_user(db_session, app):
    from app.models.rbac import RbacRole
    from tests.factories import create_test_user

    user = create_test_user(db_session, email='translator@example.com', password='Pass12345!')
    _ensure_permission(db_session, 'translations.review.use', 'Use inline translation review')
    role = db_session.query(RbacRole).filter_by(code='translator').first()
    if role is None:
        role = RbacRole(code='translator', name='Translator', description='Translator')
        db_session.add(role)
        db_session.flush()
    set_user_translator_languages(user.id, ['fr'], assigned_by_user_id=user.id)
    user.preferred_language = 'fr'
    db_session.commit()
    return user


def _login_translator(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['language'] = 'fr'


class TestTranslationReviewRoutes:
    def test_get_string_requires_assigned_locale(self, client, db_session, translator_user, translation_po_dir):
        _login_translator(client, translator_user)

        msgid_b64 = base64.b64encode(b'Dashboard').decode('ascii')
        ok = client.get(
            f'/translation-review/api/string?msgid_b64={msgid_b64}&locale=fr',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert ok.status_code == 200
        payload = ok.get_json()
        assert payload['current_translation'] == 'Tableau de bord'

        denied = client.get(
            f'/translation-review/api/string?msgid_b64={msgid_b64}&locale=en',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        # English locale is not editable via inline review.
        assert denied.status_code == 400

    def test_save_rejects_missing_placeholder(self, client, db_session, translator_user, translation_po_dir):
        _login_translator(client, translator_user)

        response = client.post(
            '/translation-review/api/string',
            data=json.dumps({
                'msgid': '%(count)d items',
                'locale': 'fr',
                'translation': 'articles',
            }),
            content_type='application/json',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert response.status_code == 400

    def test_save_updates_po_and_compiles(self, client, db_session, translator_user, translation_po_dir):
        po_path = os.path.join(translation_po_dir, 'fr', 'LC_MESSAGES', 'messages.po')
        po = polib.pofile(po_path)
        po.append(polib.POEntry(msgid='%(count)d items', msgstr='%(count)d articles'))
        po.save(po_path)

        _login_translator(client, translator_user)

        response = client.post(
            '/translation-review/api/string',
            data=json.dumps({
                'msgid': '%(count)d items',
                'locale': 'fr',
                'translation': '%(count)d elements',
            }),
            content_type='application/json',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert response.status_code == 200

        updated = polib.pofile(po_path).find('%(count)d items')
        assert updated.msgstr == '%(count)d elements'
        mo_path = po_path.replace('.po', '.mo')
        assert os.path.exists(mo_path)

    def test_toggle_requires_permission(self, client, db_session, app):
        from tests.factories import create_test_user

        user = create_test_user(db_session, email='plain@example.com', password='Pass12345!')
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.post(
            '/translation-review/toggle',
            data=json.dumps({}),
            content_type='application/json',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert response.status_code == 403


class TestTranslationReviewHooks:
    def test_after_request_strips_markers_from_json(self, app):
        from app.services.translation_review.marker import encode, strip

        with app.test_request_context('/api/example'):
            from flask import Response, g

            g.translation_review_active = True
            response = Response(json.dumps({'text': 'Bonjour' + encode('Hello')}), mimetype='application/json')
            data = response.get_data(as_text=True)
            cleaned = strip(data)
            assert encode('Hello') not in cleaned
            assert 'Bonjour' in cleaned

    def test_jinja_gettext_does_not_break_template_render(self, app):
        with app.test_request_context('/auth/login'):
            html = app.jinja_env.from_string('{{ _("Login") }}').render()
            assert 'Login' in html
