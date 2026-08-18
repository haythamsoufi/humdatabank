"""Approved glossary term APIs on the translation quality page."""


def test_quality_dashboard_renders_glossary_grids(logged_in_admin_client, db_session):
    from app.services.translation.glossary_terms import upsert_glossary_term

    upsert_glossary_term(
        source_term="Focal Point",
        target_term="point focal",
        target_lang="fr",
        tier="must",
    )
    resp = logged_in_admin_client.get("/admin/translations/quality")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Approved glossary" in body
    assert 'id="quality-tabs"' in body
    assert 'id="glossaryTermsGrid"' in body
    assert 'id="glossaryInboxGrid"' in body
    assert 'id="glossary-terms-bulk"' in body
    assert 'id="glossary-inbox-bulk"' in body
    assert "translation-quality-grids.js" in body
    assert "point focal" not in body


def test_create_and_deactivate_glossary_term_api(logged_in_admin_client, db_session):
    created = logged_in_admin_client.post(
        "/admin/translations/api/glossary-terms",
        json={
            "source_term": "National Society",
            "target_term": "Société nationale",
            "target_lang": "fr",
            "tier": "must",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert created.status_code == 200
    payload = created.get_json()
    assert payload["success"] is True
    term_id = payload["term"]["id"]

    listed = logged_in_admin_client.get("/admin/translations/api/glossary-terms?target_lang=fr")
    assert listed.status_code == 200
    items = listed.get_json()["items"]
    assert any(row["id"] == term_id for row in items)

    updated = logged_in_admin_client.post(
        f"/admin/translations/api/glossary-terms/{term_id}",
        json={"is_active": False},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["term"]["is_active"] is False
    hidden = logged_in_admin_client.get("/admin/translations/api/glossary-terms?target_lang=fr")
    assert all(row["id"] != term_id for row in hidden.get_json()["items"])


def test_list_and_accept_glossary_candidate_api(logged_in_admin_client, db_session):
    from app.models.translation_quality import TranslationGlossaryCandidate

    row = TranslationGlossaryCandidate(
        source_term="National Society",
        target_term="Société nationale",
        source_lang="en",
        target_lang="fr",
        extractor="test",
        confidence=0.91,
        proposed_tier="must",
        status="pending",
        evidence={"conflict": False},
    )
    db_session.add(row)
    db_session.commit()
    candidate_id = row.id

    listed = logged_in_admin_client.get("/admin/translations/api/glossary-candidates")
    assert listed.status_code == 200
    payload = listed.get_json()
    assert payload["success"] is True
    assert any(item["id"] == candidate_id for item in payload["items"])

    decided = logged_in_admin_client.post(
        f"/admin/translations/api/glossary-candidates/{candidate_id}",
        json={
            "accept": True,
            "source_term": "National Society",
            "target_term": "Société nationale",
            "tier": "must",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert decided.status_code == 200
    assert decided.get_json()["accepted"] is True

    empty = logged_in_admin_client.get("/admin/translations/api/glossary-candidates")
    assert all(item["id"] != candidate_id for item in empty.get_json()["items"])
    terms = logged_in_admin_client.get("/admin/translations/api/glossary-terms?target_lang=fr")
    assert any(item["source_term"] == "National Society" for item in terms.get_json()["items"])


def test_bulk_update_glossary_terms_api(logged_in_admin_client, db_session):
    from app.services.translation.glossary_terms import upsert_glossary_term

    first = upsert_glossary_term(
        source_term="Focal Point",
        target_term="point focal",
        target_lang="fr",
        tier="must",
    )
    second = upsert_glossary_term(
        source_term="National Society",
        target_term="Société nationale",
        target_lang="fr",
        tier="must",
    )
    resp = logged_in_admin_client.post(
        "/admin/translations/api/glossary-terms/bulk",
        json={"ids": [first["id"], second["id"]], "is_active": False, "tier": "preferred"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["updated"] == 2
    assert all(item["is_active"] is False and item["tier"] == "preferred" for item in payload["items"])


def test_bulk_decide_glossary_candidates_api(logged_in_admin_client, db_session):
    from app.models.translation_quality import TranslationGlossaryCandidate

    rows = [
        TranslationGlossaryCandidate(
            source_term="Appeal",
            target_term="appel",
            source_lang="en",
            target_lang="fr",
            extractor="test",
            confidence=0.8,
            proposed_tier="preferred",
            status="pending",
        ),
        TranslationGlossaryCandidate(
            source_term="Operation",
            target_term="opération",
            source_lang="en",
            target_lang="fr",
            extractor="test",
            confidence=0.7,
            proposed_tier="must",
            status="pending",
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()
    ids = [row.id for row in rows]

    rejected = logged_in_admin_client.post(
        "/admin/translations/api/glossary-candidates/bulk",
        json={"accept": False, "ids": ids},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["updated"] == 2
    leftover = logged_in_admin_client.get("/admin/translations/api/glossary-candidates")
    assert leftover.get_json()["items"] == []
