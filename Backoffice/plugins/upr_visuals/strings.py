"""Static UPR visual chrome — system-language translations (no live API).

Keys are the English display strings passed to ``t()``. Pattern keys use
``{slot}``, ``{year}``, ``{start}``, and ``{end}``. Matcher constants in
``catalog.py`` stay English and are not listed here.
"""

from __future__ import annotations

import re

_LANGS = ("fr", "es", "ar", "ru", "zh")

# msgid, {lang: translation}. Every language must be present for each row.
_ROWS: tuple[tuple[str, dict[str, str]], ...] = (
    # Dashboard titles / chips
    ("All visuals", {
        "fr": "Tous les visuels",
        "es": "Todos los visuales",
        "ar": "جميع الرسوم",
        "ru": "Все визуализации",
        "zh": "全部可视化",
    }),
    ("In Support of", {
        "fr": "En soutien à",
        "es": "En apoyo de",
        "ar": "دعمًا لـ",
        "ru": "В поддержку",
        "zh": "支持",
    }),
    ("In support of", {
        "fr": "En soutien à",
        "es": "En apoyo de",
        "ar": "دعمًا لـ",
        "ru": "В поддержку",
        "zh": "支持",
    }),
    ("IN SUPPORT OF", {
        "fr": "EN SOUTIEN À",
        "es": "EN APOYO DE",
        "ar": "دعمًا لـ",
        "ru": "В ПОДДЕРЖКУ",
        "zh": "支持",
    }),
    ("People reached", {
        "fr": "Personnes atteintes",
        "es": "Personas alcanzadas",
        "ar": "الأشخاص الذين تم الوصول إليهم",
        "ru": "Охват населения",
        "zh": "惠及人数",
    }),
    ("People to be reached", {
        "fr": "Personnes à atteindre",
        "es": "Personas a alcanzar",
        "ar": "الأشخاص المقرر الوصول إليهم",
        "ru": "Планируемый охват",
        "zh": "拟惠及人数",
    }),
    ("Financial Overview", {
        "fr": "Aperçu financier",
        "es": "Panorama financiero",
        "ar": "لمحة مالية",
        "ru": "Финансовый обзор",
        "zh": "财务概览",
    }),
    ("FINANCIAL OVERVIEW", {
        "fr": "APERÇU FINANCIER",
        "es": "PANORAMA FINANCIERO",
        "ar": "لمحة مالية",
        "ru": "ФИНАНСОВЫЙ ОБЗОР",
        "zh": "财务概览",
    }),
    ("Funding requirements", {
        "fr": "Besoins de financement",
        "es": "Necesidades de financiación",
        "ar": "احتياجات التمويل",
        "ru": "Потребности в финансировании",
        "zh": "资金需求",
    }),
    ("Network funding", {
        "fr": "Financement du réseau",
        "es": "Financiación de la red",
        "ar": "تمويل الشبكة",
        "ru": "Финансирование сети",
        "zh": "网络资金",
    }),
    ("Network-supported activities", {
        "fr": "Activités soutenues par le réseau",
        "es": "Actividades apoyadas por la red",
        "ar": "الأنشطة المدعومة من الشبكة",
        "ru": "Мероприятия при поддержке сети",
        "zh": "网络支持的活动",
    }),
    ("IFRC Network-Supported Activities", {
        "fr": "Activités soutenues par le réseau IFRC",
        "es": "Actividades apoyadas por la red de la FICR",
        "ar": "الأنشطة المدعومة من شبكة الاتحاد الدولي",
        "ru": "Мероприятия при поддержке сети МФОККиКП",
        "zh": "IFRC网络支持的活动",
    }),
    ("Strategic Priorities", {
        "fr": "Priorités stratégiques",
        "es": "Prioridades estratégicas",
        "ar": "الأولويات الاستراتيجية",
        "ru": "Стратегические приоритеты",
        "zh": "战略重点",
    }),
    ("Enabling Functions", {
        "fr": "Fonctions habilitantes",
        "es": "Funciones habilitadoras",
        "ar": "الوظائف التمكينية",
        "ru": "Обеспечивающие функции",
        "zh": "赋能职能",
    }),
    ("Bilateral Support", {
        "fr": "Soutien bilatéral",
        "es": "Apoyo bilateral",
        "ar": "الدعم الثنائي",
        "ru": "Двусторонняя поддержка",
        "zh": "双边支持",
    }),
    ("Bilateral support", {
        "fr": "Soutien bilatéral",
        "es": "Apoyo bilateral",
        "ar": "الدعم الثنائي",
        "ru": "Двусторонняя поддержка",
        "zh": "双边支持",
    }),
    ("Participating National Societies bilateral support", {
        "fr": "Soutien bilatéral des Sociétés nationales participantes",
        "es": "Apoyo bilateral de las Sociedades Nacionales participantes",
        "ar": "الدعم الثنائي من الجمعيات الوطنية المشاركة",
        "ru": "Двусторонняя поддержка участвующих национальных обществ",
        "zh": "参与国家红会的双边支持",
    }),
    ("Emergency {slot}", {
        "fr": "Urgence {slot}",
        "es": "Emergencia {slot}",
        "ar": "الطوارئ {slot}",
        "ru": "Чрезвычайная ситуация {slot}",
        "zh": "紧急情况 {slot}",
    }),
    # KPI figures
    ("Local Branches", {
        "fr": "Sections locales",
        "es": "Filiales locales",
        "ar": "الفروع المحلية",
        "ru": "Местные отделения",
        "zh": "地方分会",
    }),
    ("Branches", {
        "fr": "Sections",
        "es": "Filiales",
        "ar": "الفروع",
        "ru": "Отделения",
        "zh": "分会",
    }),
    ("Local Units", {
        "fr": "Unités locales",
        "es": "Unidades locales",
        "ar": "الوحدات المحلية",
        "ru": "Местные подразделения",
        "zh": "地方单位",
    }),
    ("Local units", {
        "fr": "Unités locales",
        "es": "Unidades locales",
        "ar": "الوحدات المحلية",
        "ru": "Местные подразделения",
        "zh": "地方单位",
    }),
    ("Volunteers", {
        "fr": "Volontaires",
        "es": "Voluntarios",
        "ar": "المتطوعون",
        "ru": "Добровольцы",
        "zh": "志愿者",
    }),
    ("Paid Staff", {
        "fr": "Personnel rémunéré",
        "es": "Personal remunerado",
        "ar": "الموظفون بأجر",
        "ru": "Оплачиваемый персонал",
        "zh": "受薪职员",
    }),
    ("Staff", {
        "fr": "Personnel",
        "es": "Personal",
        "ar": "الموظفون",
        "ru": "Персонал",
        "zh": "职员",
    }),
    # Areas
    ("Emergency Operations", {
        "fr": "Opérations d'urgence",
        "es": "Operaciones de emergencia",
        "ar": "العمليات الطارئة",
        "ru": "Чрезвычайные операции",
        "zh": "紧急行动",
    }),
    ("Cross-cutting", {
        "fr": "Transversal",
        "es": "Transversal",
        "ar": "مشترك بين القطاعات",
        "ru": "Сквозные темы",
        "zh": "跨领域",
    }),
    ("Climate and environment", {
        "fr": "Climat et environnement",
        "es": "Clima y medio ambiente",
        "ar": "المناخ والبيئة",
        "ru": "Климат и окружающая среда",
        "zh": "气候与环境",
    }),
    ("Disasters and crises", {
        "fr": "Catastrophes et crises",
        "es": "Desastres y crisis",
        "ar": "الكوارث والأزمات",
        "ru": "Бедствия и кризисы",
        "zh": "灾害与危机",
    }),
    ("Disasters & crises", {
        "fr": "Catastrophes et crises",
        "es": "Desastres y crisis",
        "ar": "الكوارث والأزمات",
        "ru": "Бедствия и кризисы",
        "zh": "灾害与危机",
    }),
    ("Health and wellbeing", {
        "fr": "Santé et bien-être",
        "es": "Salud y bienestar",
        "ar": "الصحة والرفاه",
        "ru": "Здоровье и благополучие",
        "zh": "健康与福祉",
    }),
    ("Health & wellbeing", {
        "fr": "Santé et bien-être",
        "es": "Salud y bienestar",
        "ar": "الصحة والرفاه",
        "ru": "Здоровье и благополучие",
        "zh": "健康与福祉",
    }),
    ("Migration and displacement", {
        "fr": "Migration et déplacement",
        "es": "Migración y desplazamiento",
        "ar": "الهجرة والنزوح",
        "ru": "Миграция и перемещение",
        "zh": "移民与流离失所",
    }),
    ("Migration & displacement", {
        "fr": "Migration et déplacement",
        "es": "Migración y desplazamiento",
        "ar": "الهجرة والنزوح",
        "ru": "Миграция и перемещение",
        "zh": "移民与流离失所",
    }),
    ("Values, power and inclusion", {
        "fr": "Valeurs, pouvoir et inclusion",
        "es": "Valores, poder e inclusión",
        "ar": "القيم والسلطة والإدماج",
        "ru": "Ценности, власть и инклюзия",
        "zh": "价值观、权力与包容",
    }),
    ("Values, power & inclusion", {
        "fr": "Valeurs, pouvoir et inclusion",
        "es": "Valores, poder e inclusión",
        "ar": "القيم والسلطة والإدماج",
        "ru": "Ценности, власть и инклюзия",
        "zh": "价值观、权力与包容",
    }),
    ("Strategic and operational coordination", {
        "fr": "Coordination stratégique et opérationnelle",
        "es": "Coordinación estratégica y operacional",
        "ar": "التنسيق الاستراتيجي والتشغيلي",
        "ru": "Стратегическая и оперативная координация",
        "zh": "战略与行动协调",
    }),
    ("National Society development", {
        "fr": "Développement des Sociétés nationales",
        "es": "Desarrollo de las Sociedades Nacionales",
        "ar": "تنمية الجمعيات الوطنية",
        "ru": "Развитие национальных обществ",
        "zh": "国家红会发展",
    }),
    ("Humanitarian diplomacy", {
        "fr": "Diplomatie humanitaire",
        "es": "Diplomacia humanitaria",
        "ar": "الدبلوماسية الإنسانية",
        "ru": "Гуманитарная дипломатия",
        "zh": "人道主义外交",
    }),
    ("Accountability and agility", {
        "fr": "Redevabilité et agilité",
        "es": "Rendición de cuentas y agilidad",
        "ar": "المساءلة والمرونة",
        "ru": "Подотчётность и гибкость",
        "zh": "问责与敏捷",
    }),
    # Finance / support
    ("Funding Requirement", {
        "fr": "Besoin de financement",
        "es": "Necesidad de financiación",
        "ar": "احتياج التمويل",
        "ru": "Потребность в финансировании",
        "zh": "资金需求",
    }),
    ("Funding requirement", {
        "fr": "Besoin de financement",
        "es": "Necesidad de financiación",
        "ar": "احتياج التمويل",
        "ru": "Потребность в финансировании",
        "zh": "资金需求",
    }),
    ("Confirmed Funding", {
        "fr": "Financement confirmé",
        "es": "Financiación confirmada",
        "ar": "التمويل المؤكد",
        "ru": "Подтверждённое финансирование",
        "zh": "已确认资金",
    }),
    ("Funding Reported", {
        "fr": "Financement déclaré",
        "es": "Financiación declarada",
        "ar": "التمويل المُبلَّغ عنه",
        "ru": "Заявленное финансирование",
        "zh": "已报告资金",
    }),
    ("Funding", {
        "fr": "Financement",
        "es": "Financiación",
        "ar": "التمويل",
        "ru": "Финансирование",
        "zh": "资金",
    }),
    ("Expenditure", {
        "fr": "Dépenses",
        "es": "Gasto",
        "ar": "النفقات",
        "ru": "Расходы",
        "zh": "支出",
    }),
    ("Not reported", {
        "fr": "Non communiqué",
        "es": "No comunicado",
        "ar": "غير مُبلَّغ",
        "ru": "Не представлено",
        "zh": "未报告",
    }),
    ("Country", {
        "fr": "Pays",
        "es": "País",
        "ar": "البلد",
        "ru": "Страна",
        "zh": "国家",
    }),
    ("Year", {
        "fr": "Année",
        "es": "Año",
        "ar": "السنة",
        "ru": "Год",
        "zh": "年份",
    }),
    ("Total", {
        "fr": "Total",
        "es": "Total",
        "ar": "المجموع",
        "ru": "Итого",
        "zh": "合计",
    }),
    ("Longer-term", {
        "fr": "Long terme",
        "es": "Largo plazo",
        "ar": "طويل الأجل",
        "ru": "Долгосрочные",
        "zh": "长期",
    }),
    ("Through Host National Society", {
        "fr": "Par la Société nationale hôte",
        "es": "A través de la Sociedad Nacional anfitriona",
        "ar": "عبر الجمعية الوطنية المضيفة",
        "ru": "Через принимающее национальное общество",
        "zh": "通过东道国家红会",
    }),
    ("Through the IFRC", {
        "fr": "Par la FICR",
        "es": "A través de la FICR",
        "ar": "عبر الاتحاد الدولي",
        "ru": "Через МФОККиКП",
        "zh": "通过IFRC",
    }),
    ("Through Participating National Societies", {
        "fr": "Par les Sociétés nationales participantes",
        "es": "A través de las Sociedades Nacionales participantes",
        "ar": "عبر الجمعيات الوطنية المشاركة",
        "ru": "Через участвующие национальные общества",
        "zh": "通过参与国家红会",
    }),
    ("Host National Society", {
        "fr": "Société nationale hôte",
        "es": "Sociedad Nacional anfitriona",
        "ar": "الجمعية الوطنية المضيفة",
        "ru": "Принимающее национальное общество",
        "zh": "东道国家红会",
    }),
    ("IFRC Secretariat", {
        "fr": "Secrétariat de la FICR",
        "es": "Secretaría de la FICR",
        "ar": "أمانة الاتحاد الدولي",
        "ru": "Секретариат МФОККиКП",
        "zh": "IFRC秘书处",
    }),
    ("IFRC", {
        "fr": "FICR",
        "es": "FICR",
        "ar": "الاتحاد الدولي",
        "ru": "МФОККиКП",
        "zh": "IFRC",
    }),
    ("Participating National Societies", {
        "fr": "Sociétés nationales participantes",
        "es": "Sociedades Nacionales participantes",
        "ar": "الجمعيات الوطنية المشاركة",
        "ru": "Участвующие национальные общества",
        "zh": "参与国家红会",
    }),
    ("HNS other funding sources", {
        "fr": "Autres sources de financement de la SNH",
        "es": "Otras fuentes de financiación de la SNA",
        "ar": "مصادر تمويل أخرى للجمعية الوطنية المضيفة",
        "ru": "Прочие источники финансирования НО",
        "zh": "东道国家红会其他资金来源",
    }),
    ("National Society", {
        "fr": "Société nationale",
        "es": "Sociedad Nacional",
        "ar": "الجمعية الوطنية",
        "ru": "Национальное общество",
        "zh": "国家红会",
    }),
    ("Appeal number", {
        "fr": "Numéro d'appel",
        "es": "Número de llamamiento",
        "ar": "رقم النداء",
        "ru": "Номер апелляции",
        "zh": "呼吁编号",
    }),
    ("ONGOING EMERGENCY INDICATORS", {
        "fr": "INDICATEURS DES URGENCES EN COURS",
        "es": "INDICADORES DE EMERGENCIAS EN CURSO",
        "ar": "مؤشرات حالات الطوارئ الجارية",
        "ru": "ПОКАЗАТЕЛИ ТЕКУЩИХ ЧРЕЗВЫЧАЙНЫХ СИТУАЦИЙ",
        "zh": "正在进行的紧急情况指标",
    }),
    ("No people-reached figures reported.", {
        "fr": "Aucun chiffre de personnes atteintes n'a été communiqué.",
        "es": "No se comunicaron cifras de personas alcanzadas.",
        "ar": "لم يُبلَّغ عن أرقام للأشخاص الذين تم الوصول إليهم.",
        "ru": "Данные об охвате населения не представлены.",
        "zh": "未报告惠及人数。",
    }),
    (
        "Information on data scope and limitations is available on the back page",
        {
            "fr": "Des informations sur la portée et les limites des données figurent au verso",
            "es": "La información sobre el alcance y las limitaciones de los datos figura en la contraportada",
            "ar": "تتوفر معلومات عن نطاق البيانات وحدودها في الصفحة الخلفية",
            "ru": "Сведения об охвате и ограничениях данных приведены на оборотной стороне",
            "zh": "有关数据范围与局限的说明见封底",
        },
    ),
    (
        "International Federation of Red Cross and Red Crescent Societies",
        {
            "fr": "Fédération internationale des Sociétés de la Croix-Rouge et du Croissant-Rouge",
            "es": "Federación Internacional de Sociedades de la Cruz Roja y de la Media Luna Roja",
            "ar": "الاتحاد الدولي لجمعيات الصليب الأحمر والهلال الأحمر",
            "ru": "Международная Федерация обществ Красного Креста и Красного Полумесяца",
            "zh": "红十字会与红新月会国际联合会",
        },
    ),
    (
        "National Societies which have contributed only multilaterally through the IFRC in {year}.",
        {
            "fr": "Sociétés nationales n'ayant contribué que de manière multilatérale par l'intermédiaire de la FICR en {year}.",
            "es": "Sociedades Nacionales que han contribuido únicamente de forma multilateral a través de la FICR en {year}.",
            "ar": "الجمعيات الوطنية التي ساهمت فقط بشكل متعدد الأطراف عبر الاتحاد الدولي في عام {year}.",
            "ru": "Национальные общества, оказавшие поддержку в {year} только на многосторонней основе через МФОККиКП.",
            "zh": "仅通过IFRC以多边方式在{year}年提供支持的国家红会。",
        },
    ),
    ("Multilateral support only", {
        "fr": "Soutien multilatéral uniquement",
        "es": "Solo apoyo multilateral",
        "ar": "دعم متعدد الأطراف فقط",
        "ru": "Только многосторонняя поддержка",
        "zh": "仅多边支持",
    }),
    ("Projected funding requirements", {
        "fr": "Besoins de financement projetés",
        "es": "Necesidades de financiación previstas",
        "ar": "احتياجات التمويل المتوقعة",
        "ru": "Прогнозируемые потребности в финансировании",
        "zh": "预计资金需求",
    }),
    ("No funding requirements reported.", {
        "fr": "Aucun besoin de financement n'a été communiqué.",
        "es": "No se comunicaron necesidades de financiación.",
        "ar": "لم يُبلَّغ عن احتياجات تمويل.",
        "ru": "Потребности в финансировании не представлены.",
        "zh": "未报告资金需求。",
    }),
    ("IFRC network Funding Requirements", {
        "fr": "Besoins de financement du réseau IFRC",
        "es": "Necesidades de financiación de la red de la FICR",
        "ar": "احتياجات تمويل شبكة الاتحاد الدولي",
        "ru": "Потребности сети МФОККиКП в финансировании",
        "zh": "IFRC网络资金需求",
    }),
    ("Detailed funding requirements", {
        "fr": "Besoins de financement détaillés",
        "es": "Necesidades de financiación detalladas",
        "ar": "احتياجات التمويل التفصيلية",
        "ru": "Подробные потребности в финансировании",
        "zh": "详细资金需求",
    }),
    ("Ongoing emergencies", {
        "fr": "Urgences en cours",
        "es": "Emergencias en curso",
        "ar": "حالات الطوارئ الجارية",
        "ru": "Текущие чрезвычайные ситуации",
        "zh": "正在进行的紧急情况",
    }),
    ("Longer-term needs", {
        "fr": "Besoins à plus long terme",
        "es": "Necesidades a más largo plazo",
        "ar": "الاحتياجات الأطول أجلاً",
        "ru": "Долгосрочные потребности",
        "zh": "较长期需求",
    }),
    ("Enabling local actors", {
        "fr": "Renforcement des acteurs locaux",
        "es": "Fortalecimiento de los actores locales",
        "ar": "تمكين الجهات الفاعلة المحلية",
        "ru": "Укрепление местных субъектов",
        "zh": "赋能地方行动方",
    }),
    ("CHF", {
        "fr": "CHF",
        "es": "CHF",
        "ar": "فرنك سويسري",
        "ru": "CHF",
        "zh": "CHF",
    }),
    ("in Swiss francs (CHF)", {
        "fr": "en francs suisses (CHF)",
        "es": "en francos suizos (CHF)",
        "ar": "بالفرنك السويسري (CHF)",
        "ru": "в швейцарских франках (CHF)",
        "zh": "以瑞士法郎计 (CHF)",
    }),
    ("No funding sources reported.", {
        "fr": "Aucune source de financement n'a été communiquée.",
        "es": "No se comunicaron fuentes de financiación.",
        "ar": "لم يُبلَّغ عن مصادر تمويل.",
        "ru": "Источники финансирования не представлены.",
        "zh": "未报告资金来源。",
    }),
    ("Overview", {
        "fr": "Aperçu",
        "es": "Resumen",
        "ar": "نظرة عامة",
        "ru": "Обзор",
        "zh": "概览",
    }),
    ("Funding Sources", {
        "fr": "Sources de financement",
        "es": "Fuentes de financiación",
        "ar": "مصادر التمويل",
        "ru": "Источники финансирования",
        "zh": "资金来源",
    }),
    ("IFRC network", {
        "fr": "Réseau IFRC",
        "es": "Red de la FICR",
        "ar": "شبكة الاتحاد الدولي",
        "ru": "Сеть МФОККиКП",
        "zh": "IFRC网络",
    }),
    ("No participating National Societies reported.", {
        "fr": "Aucune Société nationale participante n'a été communiquée.",
        "es": "No se comunicaron Sociedades Nacionales participantes.",
        "ar": "لم يُبلَّغ عن جمعيات وطنية مشاركة.",
        "ru": "Участвующие национальные общества не указаны.",
        "zh": "未报告参与国家红会。",
    }),
    ("No core indicators reported.", {
        "fr": "Aucun indicateur de base n'a été communiqué.",
        "es": "No se comunicaron indicadores básicos.",
        "ar": "لم يُبلَّغ عن مؤشرات أساسية.",
        "ru": "Основные показатели не представлены.",
        "zh": "未报告核心指标。",
    }),
    ("No enabling-function indicators reported.", {
        "fr": "Aucun indicateur des fonctions habilitantes n'a été communiqué.",
        "es": "No se comunicaron indicadores de las funciones habilitadoras.",
        "ar": "لم يُبلَّغ عن مؤشرات الوظائف التمكينية.",
        "ru": "Показатели обеспечивающих функций не представлены.",
        "zh": "未报告赋能职能指标。",
    }),
    ("No emergency appeal selected for this slot.", {
        "fr": "Aucun appel d'urgence n'a été sélectionné pour cet emplacement.",
        "es": "No se seleccionó ningún llamamiento de emergencia para esta casilla.",
        "ar": "لم يُحدد نداء طوارئ لهذه الخانة.",
        "ru": "Для этого слота не выбран чрезвычайный апелль.",
        "zh": "此栏未选择紧急呼吁。",
    }),
    ("Yes", {
        "fr": "Oui",
        "es": "Sí",
        "ar": "نعم",
        "ru": "Да",
        "zh": "是",
    }),
    ("No", {
        "fr": "Non",
        "es": "No",
        "ar": "لا",
        "ru": "Нет",
        "zh": "否",
    }),
    ("ADDITIONAL INFORMATION", {
        "fr": "INFORMATIONS COMPLÉMENTAIRES",
        "es": "INFORMACIÓN ADICIONAL",
        "ar": "معلومات إضافية",
        "ru": "ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ",
        "zh": "补充信息",
    }),
    # Cover / folio lines
    ("IFRC network country plan", {
        "fr": "Plan pays du réseau IFRC",
        "es": "Plan de país de la red de la FICR",
        "ar": "خطة البلد لشبكة الاتحاد الدولي",
        "ru": "Страновой план сети МФОККиКП",
        "zh": "IFRC网络国家计划",
    }),
    ("{year} IFRC network country plan", {
        "fr": "Plan pays du réseau IFRC {year}",
        "es": "Plan de país de la red de la FICR {year}",
        "ar": "خطة البلد لشبكة الاتحاد الدولي {year}",
        "ru": "Страновой план сети МФОККиКП {year}",
        "zh": "{year} 年IFRC网络国家计划",
    }),
    ("{start}-{end} IFRC network country plan", {
        "fr": "Plan pays du réseau IFRC {start}-{end}",
        "es": "Plan de país de la red de la FICR {start}-{end}",
        "ar": "خطة البلد لشبكة الاتحاد الدولي {start}-{end}",
        "ru": "Страновой план сети МФОККиКП {start}-{end}",
        "zh": "{start}-{end} 年IFRC网络国家计划",
    }),
    ("IFRC network mid-year report, Jan-Jun", {
        "fr": "Rapport semestriel du réseau IFRC, janv.-juin",
        "es": "Informe de mitad de año de la red de la FICR, ene-jun",
        "ar": "التقرير النصفي لشبكة الاتحاد الدولي، يناير-يونيو",
        "ru": "Полугодовой отчёт сети МФОККиКП, янв.–июн.",
        "zh": "IFRC网络年中报告，1–6月",
    }),
    ("{year} IFRC network mid-year report, Jan-Jun", {
        "fr": "Rapport semestriel du réseau IFRC {year}, janv.-juin",
        "es": "Informe de mitad de año de la red de la FICR {year}, ene-jun",
        "ar": "التقرير النصفي لشبكة الاتحاد الدولي {year}، يناير-يونيو",
        "ru": "Полугодовой отчёт сети МФОККиКП {year}, янв.–июн.",
        "zh": "{year} 年IFRC网络年中报告，1–6月",
    }),
    ("IFRC network annual report, Jan-Dec", {
        "fr": "Rapport annuel du réseau IFRC, janv.-déc.",
        "es": "Informe anual de la red de la FICR, ene-dic",
        "ar": "التقرير السنوي لشبكة الاتحاد الدولي، يناير-ديسمبر",
        "ru": "Годовой отчёт сети МФОККиКП, янв.–дек.",
        "zh": "IFRC网络年度报告，1–12月",
    }),
    ("{year} IFRC network annual report, Jan-Dec", {
        "fr": "Rapport annuel du réseau IFRC {year}, janv.-déc.",
        "es": "Informe anual de la red de la FICR {year}, ene-dic",
        "ar": "التقرير السنوي لشبكة الاتحاد الدولي {year}، يناير-ديسمبر",
        "ru": "Годовой отчёт сети МФОККиКП {year}, янв.–дек.",
        "zh": "{year} 年IFRC网络年度报告，1–12月",
    }),
    ("Unified Country Report", {
        "fr": "Rapport de pays unifié",
        "es": "Informe de país unificado",
        "ar": "التقرير القطري الموحد",
        "ru": "Единый страновой отчёт",
        "zh": "统一国家报告",
    }),
    ("Unified Country Plan", {
        "fr": "Plan de pays unifié",
        "es": "Plan de país unificado",
        "ar": "الخطة القطرية الموحدة",
        "ru": "Единый страновой план",
        "zh": "统一国家计划",
    }),
    ("Unified Plan", {
        "fr": "Plan unifié",
        "es": "Plan unificado",
        "ar": "الخطة الموحدة",
        "ru": "Единый план",
        "zh": "统一计划",
    }),
    ("IFRC network unified plan", {
        "fr": "Plan unifié du réseau IFRC",
        "es": "Plan unificado de la red de la FICR",
        "ar": "الخطة الموحدة لشبكة الاتحاد الدولي",
        "ru": "Единый план сети МФОККиКП",
        "zh": "IFRC网络统一计划",
    }),
    ("{year} IFRC network unified plan", {
        "fr": "Plan unifié du réseau IFRC {year}",
        "es": "Plan unificado de la red de la FICR {year}",
        "ar": "الخطة الموحدة لشبكة الاتحاد الدولي {year}",
        "ru": "Единый план сети МФОККиКП {year}",
        "zh": "{year} 年IFRC网络统一计划",
    }),
    ("IFRC network annual report", {
        "fr": "Rapport annuel du réseau IFRC",
        "es": "Informe anual de la red de la FICR",
        "ar": "التقرير السنوي لشبكة الاتحاد الدولي",
        "ru": "Годовой отчёт сети МФОККиКП",
        "zh": "IFRC网络年度报告",
    }),
    ("{year} IFRC network annual report", {
        "fr": "Rapport annuel du réseau IFRC {year}",
        "es": "Informe anual de la red de la FICR {year}",
        "ar": "التقرير السنوي لشبكة الاتحاد الدولي {year}",
        "ru": "Годовой отчёт сети МФОККиКП {year}",
        "zh": "{year} 年IFRC网络年度报告",
    }),
)

_PATTERNS: tuple[tuple[re.Pattern[str], str, tuple[str, ...]], ...] = (
    (re.compile(r"^Emergency (\d+)$"), "Emergency {slot}", ("slot",)),
    (re.compile(r"^(\d{4})-(\d{4}) IFRC network country plan$"), "{start}-{end} IFRC network country plan", ("start", "end")),
    (re.compile(r"^(\d{4}) IFRC network country plan$"), "{year} IFRC network country plan", ("year",)),
    (re.compile(r"^(\d{4}) IFRC network mid-year report, Jan-Jun$"), "{year} IFRC network mid-year report, Jan-Jun", ("year",)),
    (re.compile(r"^(\d{4}) IFRC network annual report, Jan-Dec$"), "{year} IFRC network annual report, Jan-Dec", ("year",)),
    (re.compile(r"^(\d{4}) IFRC network unified plan$"), "{year} IFRC network unified plan", ("year",)),
    (re.compile(r"^(\d{4}) IFRC network annual report$"), "{year} IFRC network annual report", ("year",)),
)


def _build_tables() -> dict[str, dict[str, str]]:
    tables = {lang: {} for lang in _LANGS}
    for msgid, translations in _ROWS:
        missing = [lang for lang in _LANGS if lang not in translations]
        if missing:
            raise ValueError(f"Missing translations {missing} for {msgid!r}")
        for lang in _LANGS:
            tables[lang][msgid] = translations[lang]
    return tables


VISUAL_STRINGS = _build_tables()


def lookup_visual_string(text: str, lang: str) -> str | None:
    """Return a catalogued translation, including year/slot pattern keys."""
    table = VISUAL_STRINGS.get(lang) or {}
    hit = table.get(text)
    if hit:
        return hit
    for pattern, template_key, names in _PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        tmpl = table.get(template_key)
        if not tmpl:
            continue
        values = {name: match.group(index + 1) for index, name in enumerate(names)}
        return tmpl.format(**values)
    return None
