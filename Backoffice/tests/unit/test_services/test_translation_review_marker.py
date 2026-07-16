"""Tests for translation review Unicode markers."""

from app.services.translation_review.marker import contains_marker, decode, encode, strip


class TestTranslationReviewMarker:
    def test_encode_decode_round_trip(self):
        msgid = 'Save %(count)d items'
        marked = 'Translated text' + encode(msgid)
        decoded = decode(marked)
        assert decoded == [msgid]

    def test_decode_multiple_markers(self):
        first = 'Hello' + encode('Hello')
        second = 'Bye' + encode('Bye')
        assert decode(first + ' ' + second) == ['Hello', 'Bye']

    def test_strip_removes_markers(self):
        msgid = 'Dashboard'
        marked = 'Tableau de bord' + encode(msgid)
        assert strip(marked) == 'Tableau de bord'
        assert not contains_marker(strip(marked))

    def test_preserves_whitespace_in_msgid(self):
        msgid = 'Label '
        marked = encode(msgid)
        assert decode('x' + marked) == [msgid]
