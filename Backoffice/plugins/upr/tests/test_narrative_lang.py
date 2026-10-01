"""Narrative source-language detection for any-to-any visuals translation."""

import pytest

from plugins.upr.narrative_lang import detect_narrative_language


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "en"),
        ("Context", "en"),
        (
            "The national society and the volunteers have been working with "
            "people from communities that were affected by the floods.",
            "en",
        ),
        (
            "La Société nationale et les volontaires apportent une aide aux "
            "communautés dans le cadre du plan et avec les partenaires.",
            "fr",
        ),
        (
            "La Sociedad Nacional y los voluntarios prestan apoyo a las "
            "comunidades desde el plan, pero también sobre el terreno.",
            "es",
        ),
        (
            "Der Nationale Gesellschaft und die Freiwilligen sind mit den "
            "Gemeinden und für die Menschen von der Krise auch nicht allein.",
            "de",
        ),
        (
            "Красный Крест оказывает помощь населению в чрезвычайных ситуациях "
            "и поддерживает общины по всей стране.",
            "ru",
        ),
        (
            "Червоний Хрест надає допомогу населенню у надзвичайних ситуаціях "
            "і підтримує громади по всій країні.",
            "uk",
        ),
        (
            "الهلال الأحمر يقدم المساعدة للسكان في حالات الطوارئ ويدعم "
            "المجتمعات في جميع أنحاء البلاد من خلال المتطوعين.",
            "ar",
        ),
        (
            "صليب سرخ کمک را به مردم در شرایط اضطراری ارائه می‌کند و جوامع "
            "را در سراسر کشور با داوطلبان پشتیبانی می‌کند.",
            "fa",
        ),
        (
            "红十字会向受灾群众提供援助，并在全国范围内支持社区开展应急工作与恢复计划。",
            "zh",
        ),
        (
            "赤十字は被災した人々を支援し、全国の地域社会で緊急対応と復旧の活動を続けています。",
            "ja",
        ),
        (
            "적십자는 재난을 겪은 사람들을 지원하고 전국의 지역사회에서 긴급 대응을 계속합니다.",
            "ko",
        ),
        (
            "रेड क्रॉस आपात स्थिति में लोगों की सहायता करता है और पूरे देश में समुदायों का समर्थन करता है।",
            "hi",
        ),
    ],
)
def test_detect_narrative_language(text, expected):
    assert detect_narrative_language(text) == expected
