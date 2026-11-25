"""Strings for Emergency Appeals. English is the key. Each value is (french, spanish, arabic)."""

from __future__ import annotations

ROWS: dict[str, tuple[str, str, str]] = {
    "Emergency Operations": (
        "Opérations d'urgence",
        "Operaciones de emergencia",
        "عمليات الطوارئ",
    ),
    "Emergency Appeal": ("Appel d'urgence", "Llamamiento de emergencia", "نداء الطوارئ"),
    "Imminent DREF": ("DREF imminent", "DREF inminente", "صندوق الطوارئ الاستباقي"),
    "Reading Emergency Appeals, page %(current)s.": (
        "Lecture des appels d'urgence, page %(current)s.",
        "Leyendo los llamamientos de emergencia, página %(current)s.",
        "جارٍ قراءة نداءات الطوارئ، الصفحة %(current)s.",
    ),
    "Sync Emergency Appeals": (
        "Synchroniser les appels d'urgence",
        "Sincronizar los llamamientos de emergencia",
        "مزامنة نداءات الطوارئ",
    ),
    "Closed Emergency Appeals started since (year)": (
        "Appels d'urgence clos commencés depuis (année)",
        "Llamamientos de emergencia cerrados iniciados desde (año)",
        "نداءات الطوارئ المغلقة التي بدأت منذ (السنة)",
    ),
    "Active Emergency Appeals are always read. Closed ones are read when they started in this year or later.": (
        "Les appels d'urgence actifs sont toujours lus. Les appels clos le sont s'ils ont commencé cette année-là ou après.",
        "Los llamamientos de emergencia activos se leen siempre. Los cerrados se leen si comenzaron en ese año o después.",
        "تُقرأ نداءات الطوارئ النشطة دائماً. وتُقرأ المغلقة إذا بدأت في هذه السنة أو بعدها.",
    ),
    "The button and the job at 05:10 UTC read response and imminent operations on the public dref3 feed, 200 at a time, and Emergency Appeals on the public appeal API. No API key. When GO marks an operation closed, the stored status becomes closed and the workflow moves to closure.": (
        "Le bouton et la tâche de 05:10 UTC lisent les opérations d'intervention et opérations imminentes du flux public dref3, 200 à la fois, et les appels d'urgence de l'API publique des appels. Sans clé d'API. Quand GO marque une opération comme close, le statut enregistré devient clos et l'étape passe à la clôture.",
        "El botón y la tarea de las 05:10 UTC leen las operaciones de respuesta y operaciones inminentes del flujo público dref3, de 200 en 200, y los llamamientos de emergencia de la API pública de llamamientos. Sin clave de API. Cuando GO marca una operación como cerrada, el estado guardado pasa a cerrado y el flujo pasa a cierre.",
        "يقرأ الزر والمهمة اليومية عند 05:10 بالتوقيت العالمي عمليات الاستجابة والعمليات الاستباقية في التغذية العامة dref3، بمعدل 200 في كل مرة، ونداءات الطوارئ من واجهة النداءات العامة. بلا مفتاح. عندما تصنّف GO عملية على أنها مغلقة، يصبح الوضع المحفوظ مغلقاً وتنتقل مرحلة العمل إلى الإغلاق.",
    ),
    "Applications still in draft or in review on GO are not on the feed. The feed has no activity list, so lines finer than a sector come from the Excel import on the operation. GO publishes no approved plan for an Emergency Appeal. When it has published an operational strategy, the monitoring plan is drafted from that document. Otherwise the plan lists the emergency indicators of the indicator bank, and the team switches off the ones the operation will not report on.": (
        "Les demandes encore en brouillon ou en examen dans GO ne figurent pas dans le flux. Le flux n'a pas de liste d'activités : les lignes plus fines qu'un secteur viennent de l'import Excel de l'opération. GO ne publie pas de plan approuvé pour un appel d'urgence. Quand une stratégie opérationnelle est publiée, le plan de suivi est rédigé à partir de ce document. Sinon, le plan liste les indicateurs d'urgence de la banque d'indicateurs, et l'équipe désactive ceux sur lesquels l'opération ne fera pas de rapport.",
        "Las solicitudes que siguen en borrador o en revisión en GO no están en el flujo. El flujo no tiene lista de actividades: las líneas más finas que un sector vienen de la importación Excel de la operación. GO no publica un plan aprobado para un llamamiento de emergencia. Cuando ha publicado una estrategia operativa, el plan de seguimiento se redacta a partir de ese documento. Si no, el plan enumera los indicadores de emergencia del banco de indicadores y el equipo desactiva los que la operación no reportará.",
        "الطلبات التي ما زالت مسودة أو قيد المراجعة في GO ليست في التغذية. التغذية بلا قائمة أنشطة، لذا البنود الأدق من القطاع تأتي من استيراد إكسل في العملية. لا تنشر GO خطة معتمدة لنداء الطوارئ. عندما تنشر استراتيجية تشغيلية، تُصاغ خطة المتابعة من ذلك المستند. وإلا تعرض الخطة مؤشرات الطوارئ من بنك المؤشرات، ويعطّل الفريق ما لن تُبلّغ عنه العملية.",
    ),
    "Active approved emergency operations from GO.": (
        "Opérations d'urgence approuvées et actives issues de GO.",
        "Operaciones de emergencia aprobadas y activas de GO.",
        "عمليات الطوارئ المعتمدة والنشطة من GO.",
    ),
    "This operation is an Emergency Appeal read from the public GO appeal API. The plan starts from the amount requested and the people targeted. GO publishes no approved plan. When an operational strategy is available, draft the monitoring plan from it. Otherwise the plan lists the emergency indicators of the indicator bank: switch off the ones this operation will not report on, then confirm. Activities can still be added here or imported from Excel.": (
        "Cette opération est un appel d'urgence lu depuis l'API publique des appels de GO. Le plan part du montant demandé et des personnes ciblées. GO ne publie pas de plan approuvé. Quand une stratégie opérationnelle est disponible, rédigez le plan de suivi à partir d'elle. Sinon, le plan liste les indicateurs d'urgence de la banque d'indicateurs : désactivez ceux sur lesquels cette opération ne fera pas de rapport, puis confirmez. Des activités peuvent encore être ajoutées ici ou importées depuis Excel.",
        "Esta operación es un llamamiento de emergencia leído de la API pública de llamamientos de GO. El plan parte del monto solicitado y de las personas objetivo. GO no publica un plan aprobado. Cuando hay una estrategia operativa, redacte el plan de seguimiento a partir de ella. Si no, el plan enumera los indicadores de emergencia del banco de indicadores: desactive los que esta operación no reportará y luego confirme. Las actividades se pueden añadir aquí o importar desde Excel.",
        "هذه العملية نداء طوارئ قُرئ من واجهة النداءات العامة في GO. تبدأ الخطة من المبلغ المطلوب والأشخاص المستهدفين. لا تنشر GO خطة معتمدة. عندما تتوفر استراتيجية تشغيلية، صيغوا خطة المتابعة منها. وإلا تعرض الخطة مؤشرات الطوارئ من بنك المؤشرات: عطّلوا ما لن تُبلّغ عنه هذه العملية ثم أكّدوا. يمكن إضافة الأنشطة هنا أو استيرادها من إكسل.",
    ),
    "GO publishes the budget and the people targeted of an Emergency Appeal, but not its sectors, indicators, or activities. The plan lists the emergency indicators of the indicator bank. Switch off the ones this operation will not report on, then confirm the plan. Add activities from the Emergency Plan of Action here, or import them from Excel.": (
        "GO publie le budget et les personnes ciblées d'un appel d'urgence, mais pas ses secteurs, indicateurs ni activités. Le plan liste les indicateurs d'urgence de la banque d'indicateurs. Désactivez ceux sur lesquels cette opération ne fera pas de rapport, puis confirmez le plan. Ajoutez ici les activités du plan d'action d'urgence, ou importez-les depuis Excel.",
        "GO publica el presupuesto y las personas objetivo de un llamamiento de emergencia, pero no sus sectores, indicadores ni actividades. El plan enumera los indicadores de emergencia del banco de indicadores. Desactive los que esta operación no reportará y luego confirme el plan. Añada aquí las actividades del plan de acción de emergencia, o impórtelas desde Excel.",
        "تنشر GO ميزانية نداء الطوارئ والأشخاص المستهدفين، لكنها لا تنشر قطاعاته ولا مؤشراته ولا أنشطته. تعرض الخطة مؤشرات الطوارئ من بنك المؤشرات. عطّل ما لن تُبلّغ عنه هذه العملية ثم أكّد الخطة. أضف هنا أنشطة خطة عمل الطوارئ أو استوردها من إكسل.",
    ),
    "Validate report": ("Valider le rapport", "Validar el informe", "اعتماد التقرير"),
    "This report is figures only. Add the chapters on the Narrative tab, or validate it and export it.": (
        "Ce rapport ne contient que des chiffres. Ajoutez les chapitres dans l'onglet Récit, ou validez-le puis exportez-le.",
        "Este informe solo tiene cifras. Añada los capítulos en la pestaña Relato, o valídelo y expórtelo.",
        "هذا التقرير أرقام فقط. أضف الفصول في تبويب السرد، أو اعتمده ثم صدّره.",
    ),
    "This report is figures only. It has no narrative chapters. Validate it, then export the Word file or the PDF.": (
        "Ce rapport ne contient que des chiffres et aucun chapitre narratif. Validez-le, puis exportez le fichier Word ou le PDF.",
        "Este informe solo tiene cifras y ningún capítulo narrativo. Valídelo y luego exporte el archivo Word o el PDF.",
        "هذا التقرير أرقام فقط وبلا فصول سردية. اعتمده ثم صدّر ملف وورد أو ملف PDF.",
    ),
    "Review the chapters, then validate. GO does not take Emergency Appeal reports from here, so export the Word file or the PDF to file it.": (
        "Relisez les chapitres, puis validez. GO ne reçoit pas les rapports d'appel d'urgence depuis ici : exportez le fichier Word ou le PDF pour le déposer.",
        "Revise los capítulos y luego valide. GO no recibe desde aquí los informes de llamamientos de emergencia: exporte el archivo Word o el PDF para presentarlo.",
        "راجع الفصول ثم اعتمد التقرير. لا تستقبل GO تقارير نداءات الطوارئ من هنا، فصدّر ملف وورد أو PDF لتقديمه.",
    ),
    "The report is validated. Download the Word file or the PDF to file it.": (
        "Le rapport est validé. Téléchargez le fichier Word ou le PDF pour le déposer.",
        "El informe está validado. Descargue el archivo Word o el PDF para presentarlo.",
        "تم اعتماد التقرير. نزّل ملف وورد أو PDF لتقديمه.",
    ),
    "Emergency Appeal reports are not sent to GO from here. Download the Word file or the PDF.": (
        "Les rapports d'appel d'urgence ne sont pas envoyés à GO depuis ici. Téléchargez le fichier Word ou le PDF.",
        "Los informes de llamamientos de emergencia no se envían a GO desde aquí. Descargue el archivo Word o el PDF.",
        "لا تُرسل تقارير نداءات الطوارئ إلى GO من هنا. نزّل ملف وورد أو PDF.",
    ),
    "Emergency Appeal Operational Update": (
        "Mise à jour opérationnelle de l'appel d'urgence",
        "Actualización operativa del llamamiento de emergencia",
        "التحديث التشغيلي لنداء الطوارئ",
    ),
    "Emergency Appeal Final Report": (
        "Rapport final de l'appel d'urgence",
        "Informe final del llamamiento de emergencia",
        "التقرير النهائي لنداء الطوارئ",
    ),
    "Total appeal budget (CHF)": (
        "Budget total de l'appel (CHF)",
        "Presupuesto total del llamamiento (CHF)",
        "إجمالي ميزانية النداء (فرنك سويسري)",
    ),
    "Use this frequency": ("Utiliser cette fréquence", "Usar esta frecuencia", "استخدام هذه الوتيرة"),
    "The reporting schedule could not be loaded.": (
        "Le calendrier de rapports n'a pas pu être chargé.",
        "No se pudo cargar el programa de informes.",
        "تعذر تحميل جدول التقارير.",
    ),
    "Saved frequency: {saved}.": (
        "Fréquence enregistrée : {saved}.",
        "Frecuencia guardada: {saved}.",
        "الوتيرة المحفوظة: {saved}.",
    ),
    "The operation has no start or end date yet, so no schedule can be shown.": (
        "L'opération n'a pas encore de date de début ou de fin : aucun calendrier ne peut être affiché.",
        "La operación aún no tiene fecha de inicio o de fin, por lo que no se puede mostrar un programa.",
        "ليس للعملية تاريخ بداية أو نهاية بعد، لذا لا يمكن عرض جدول.",
    ),
    "No reporting period falls between the start and the end date.": (
        "Aucune période de rapport ne tombe entre la date de début et la date de fin.",
        "Ningún periodo de informe cae entre la fecha de inicio y la de fin.",
        "لا توجد فترة تقارير بين تاريخ البداية وتاريخ النهاية.",
    ),
    "{count} reports, due {first} to {last}.": (
        "{count} rapports, dus du {first} au {last}.",
        "{count} informes, del {first} al {last}.",
        "{count} تقارير، من {first} إلى {last}.",
    ),
    "First period starts {first}, when the plan is confirmed.": (
        "La première période commence le {first}, à la confirmation du plan.",
        "El primer periodo empieza el {first}, al confirmar el plan.",
        "تبدأ الفترة الأولى في {first}، عند تأكيد الخطة.",
    ),
    "Showing the first {limit} periods.": (
        "Les {limit} premières périodes sont affichées.",
        "Se muestran los primeros {limit} periodos.",
        "تُعرض أول {limit} فترات.",
    ),
    "Period start": ("Début de la période", "Inicio del periodo", "بداية الفترة"),
    "Period end": ("Fin de la période", "Fin del periodo", "نهاية الفترة"),
    "Report due": ("Rapport dû le", "Informe vence el", "موعد استحقاق التقرير"),
    "Each report is due on the last day of its period.": (
        "Chaque rapport est dû le dernier jour de sa période.",
        "Cada informe vence el último día de su periodo.",
        "يستحق كل تقرير في اليوم الأخير من فترته.",
    ),
    "{on} of {all} on": ("{on} sur {all} activés", "{on} de {all} activados", "{on} من {all} مفعّلة"),
    "Report on this indicator": (
        "Suivre cet indicateur",
        "Informar sobre este indicador",
        "التبليغ عن هذا المؤشر",
    ),
    "Not monitored": ("Non suivi", "Sin seguimiento", "غير مُتابَع"),
    "Switch all on": ("Tout activer", "Activar todos", "تفعيل الكل"),
    "Switch all off": ("Tout désactiver", "Desactivar todos", "تعطيل الكل"),
    "Switch on at least one indicator before confirming the plan.": (
        "Activez au moins un indicateur avant de confirmer le plan.",
        "Active al menos un indicador antes de confirmar el plan.",
        "فعّل مؤشراً واحداً على الأقل قبل تأكيد الخطة.",
    ),
    "Choose biweekly or monthly.": (
        "Choisissez toutes les deux semaines ou mensuel.",
        "Elija quincenal o mensual.",
        "اختر كل أسبوعين أو شهرياً.",
    ),
    "The plan is confirmed or its reporting cycles are open. Portfolio staff can change the frequency under Governance.": (
        "Le plan est confirmé ou ses cycles de rapport sont ouverts. Le personnel du portefeuille peut changer la fréquence sous Gouvernance.",
        "El plan está confirmado o sus ciclos de informe están abiertos. El personal de cartera puede cambiar la frecuencia en Gobernanza.",
        "الخطة مؤكدة أو دورات تقاريرها مفتوحة. يمكن لموظفي المحفظة تغيير الوتيرة من قسم الحوكمة.",
    ),
    "The reporting frequency was saved.": (
        "La fréquence de rapport a été enregistrée.",
        "Se guardó la frecuencia de informe.",
        "تم حفظ وتيرة التقارير.",
    ),
    "Drafted from the operational strategy": (
        "Rédigé à partir de la stratégie opérationnelle",
        "Redactado a partir de la estrategia operativa",
        "صيغ من الاستراتيجية التشغيلية",
    ),
    "Draft plan from the operational strategy": (
        "Rédiger le plan à partir de la stratégie opérationnelle",
        "Redactar el plan a partir de la estrategia operativa",
        "صياغة الخطة من الاستراتيجية التشغيلية",
    ),
    "Operational strategy": (
        "Stratégie opérationnelle",
        "Estrategia operativa",
        "الاستراتيجية التشغيلية",
    ),
    "This monitoring plan was drafted from the operational strategy. Review the sectors, indicators, and activities, then confirm it.": (
        "Ce plan de suivi a été rédigé à partir de la stratégie opérationnelle. Vérifiez les secteurs, les indicateurs et les activités, puis confirmez-le.",
        "Este plan de seguimiento se redactó a partir de la estrategia operativa. Revise los sectores, los indicadores y las actividades, y después confírmelo.",
        "صيغت خطة المتابعة هذه من الاستراتيجية التشغيلية. راجعوا القطاعات والمؤشرات والأنشطة ثم أكّدوها.",
    ),
    "GO has no approved plan for this appeal. An operational strategy is available: draft the monitoring plan from it.": (
        "GO n'a pas de plan approuvé pour cet appel. Une stratégie opérationnelle est disponible : rédigez le plan de suivi à partir d'elle.",
        "GO no tiene un plan aprobado para este llamamiento. Hay una estrategia operativa: redacte el plan de seguimiento a partir de ella.",
        "ليس لدى GO خطة معتمدة لهذا النداء. تتوفر استراتيجية تشغيلية: صيغوا خطة المتابعة منها.",
    ),
    "The monitoring plan was drafted from the operational strategy.": (
        "Le plan de suivi a été rédigé à partir de la stratégie opérationnelle.",
        "El plan de seguimiento se redactó a partir de la estrategia operativa.",
        "صيغت خطة المتابعة من الاستراتيجية التشغيلية.",
    ),
    "Only an Emergency Appeal is drafted from an operational strategy.": (
        "Seul un appel d'urgence est rédigé à partir d'une stratégie opérationnelle.",
        "Solo un llamamiento de emergencia se redacta a partir de una estrategia operativa.",
        "لا تُصاغ من الاستراتيجية التشغيلية إلا خطة نداء طوارئ.",
    ),
    "GO has not published an operational strategy for this appeal.": (
        "GO n'a pas publié de stratégie opérationnelle pour cet appel.",
        "GO no ha publicado una estrategia operativa para este llamamiento.",
        "لم تنشر GO استراتيجية تشغيلية لهذا النداء.",
    ),
    "This plan was edited or confirmed, so it was left as it is.": (
        "Ce plan a été modifié ou confirmé, il est donc laissé tel quel.",
        "Este plan fue editado o confirmado, así que se dejó como estaba.",
        "عُدّلت هذه الخطة أو أُكّدت، فتُركت كما هي.",
    ),
    "Turn on AI draft reports before drafting a plan from the operational strategy.": (
        "Activez les brouillons de rapport par IA avant de rédiger un plan à partir de la stratégie opérationnelle.",
        "Active los borradores de informe con IA antes de redactar un plan a partir de la estrategia operativa.",
        "فعّلوا مسودات التقارير بالذكاء الاصطناعي قبل صياغة خطة من الاستراتيجية التشغيلية.",
    ),
    "The operational strategy could not be read.": (
        "La stratégie opérationnelle n'a pas pu être lue.",
        "No se pudo leer la estrategia operativa.",
        "تعذّر قراءة الاستراتيجية التشغيلية.",
    ),
    "The operational strategy did not yield a monitoring plan.": (
        "La stratégie opérationnelle n'a pas donné de plan de suivi.",
        "La estrategia operativa no produjo un plan de seguimiento.",
        "لم تُنتج الاستراتيجية التشغيلية خطة متابعة.",
    ),
    "The monitoring plan could not be drafted from the operational strategy.": (
        "Le plan de suivi n'a pas pu être rédigé à partir de la stratégie opérationnelle.",
        "No se pudo redactar el plan de seguimiento a partir de la estrategia operativa.",
        "تعذّر صياغة خطة المتابعة من الاستراتيجية التشغيلية.",
    ),
    "Drafting monitoring plans from operational strategies (%(current)s of %(total)s).": (
        "Rédaction des plans de suivi à partir des stratégies opérationnelles (%(current)s sur %(total)s).",
        "Redactando planes de seguimiento a partir de las estrategias operativas (%(current)s de %(total)s).",
        "جارٍ صياغة خطط المتابعة من الاستراتيجيات التشغيلية (%(current)s من %(total)s).",
    ),
}
