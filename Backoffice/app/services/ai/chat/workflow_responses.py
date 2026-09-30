"""Keyword matching and HTML tour replies for chatbot how-to questions.

Split out of ``helpers``. Re-exported from ``helpers`` for existing imports.
"""
import logging

logger = logging.getLogger("app.services.ai.chat.helpers")


def _normalize_language(language):
    from app.services.ai.chat.helpers import normalize_chatbot_language
    return normalize_chatbot_language(language)


def _workflow_service():
    from app.services.ai.chat.helpers import _get_workflow_service
    return _get_workflow_service()


# ============================================================================
# Workflow-based Response Generation
# ============================================================================

# Keywords that indicate a workflow/how-to question (multi-language)
WORKFLOW_KEYWORDS = [
    # English
    'how do i', 'how to', 'how can i', 'guide me', 'show me how',
    'steps to', 'step by step', 'walk me through', 'help me with',
    'tutorial', 'workflow', 'process for', 'procedure', 'instructions',
    # French
    'comment', 'comment faire', 'comment puis-je', 'guide-moi', 'montre-moi',
    'étapes pour', 'étape par étape', 'tutoriel', 'procédure', 'instructions',
    # Spanish
    'cómo', 'como', 'cómo puedo', 'como puedo', 'guíame', 'muéstrame',
    'pasos para', 'paso a paso', 'tutorial', 'procedimiento', 'instrucciones',
    # Arabic
    'كيف', 'كيفية', 'كيف يمكنني', 'ارشدني', 'اظهر لي', 'أرني',
    'خطوات', 'خطوة بخطوة', 'دليل', 'إجراء', 'تعليمات'
]

# Map of workflow IDs to their trigger keywords (multi-language)
WORKFLOW_TRIGGERS = {
    'add-user': [
        # English
        'add user', 'new user', 'create user', 'add a user', 'create account', 'add staff',
        # French
        'ajouter utilisateur', 'nouvel utilisateur', 'créer utilisateur', 'nouveau compte',
        # Spanish
        'agregar usuario', 'nuevo usuario', 'crear usuario', 'nueva cuenta',
        # Arabic
        'اضافة مستخدم', 'مستخدم جديد', 'انشاء مستخدم', 'إنشاء حساب', 'اضيف مستخدم', 'أضيف مستخدم'
    ],
    'manage-users': [
        # English
        'manage user', 'edit user', 'update user', 'modify user', 'deactivate user', 'reset password',
        # French
        'gérer utilisateur', 'modifier utilisateur', 'désactiver utilisateur', 'réinitialiser mot de passe',
        # Spanish
        'gestionar usuario', 'editar usuario', 'modificar usuario', 'desactivar usuario', 'restablecer contraseña',
        # Arabic
        'إدارة المستخدمين', 'تعديل مستخدم', 'تحديث مستخدم', 'إلغاء تنشيط مستخدم', 'إعادة تعيين كلمة المرور'
    ],
    'create-template': [
        # English
        'create template', 'new template', 'build form', 'design form', 'make template',
        # French
        'créer modèle', 'nouveau modèle', 'construire formulaire', 'concevoir formulaire',
        # Spanish
        'crear plantilla', 'nueva plantilla', 'construir formulario', 'diseñar formulario',
        # Arabic
        'إنشاء قالب', 'قالب جديد', 'بناء نموذج', 'تصميم نموذج'
    ],
    'manage-assignments': [
        # English
        'create assignment', 'assign form', 'distribute', 'assign to country', 'manage assignment',
        # French
        'créer affectation', 'attribuer formulaire', 'distribuer', 'affecter au pays',
        # Spanish
        'crear asignación', 'asignar formulario', 'distribuir', 'asignar a país',
        # Arabic
        'إنشاء تعيين', 'تعيين نموذج', 'توزيع', 'تعيين لدولة'
    ],
    'view-assignments': [
        # English
        'my assignments', 'pending tasks', 'my tasks', 'what should i do', 'my work',
        # French
        'mes affectations', 'tâches en attente', 'mes tâches', 'que dois-je faire', 'mon travail',
        # Spanish
        'mis asignaciones', 'tareas pendientes', 'mis tareas', 'qué debo hacer', 'mi trabajo',
        # Arabic
        'تعييناتي', 'المهام المعلقة', 'مهامي', 'ماذا يجب أن أفعل', 'عملي'
    ],
    'submit-data': [
        # English
        'submit data', 'fill form', 'enter data', 'complete form', 'data entry',
        # French
        'soumettre données', 'remplir formulaire', 'saisir données', 'compléter formulaire',
        # Spanish
        'enviar datos', 'llenar formulario', 'ingresar datos', 'completar formulario',
        # Arabic
        'تقديم البيانات', 'ملء النموذج', 'إدخال البيانات', 'إكمال النموذج'
    ],
    'account-settings': [
        # English
        'account settings', 'change password', 'update profile', 'my settings', 'profile settings',
        # French
        'paramètres du compte', 'changer mot de passe', 'mettre à jour profil', 'mes paramètres',
        # Spanish
        'configuración de cuenta', 'cambiar contraseña', 'actualizar perfil', 'mi configuración',
        # Arabic
        'إعدادات الحساب', 'تغيير كلمة المرور', 'تحديث الملف الشخصي', 'إعداداتي'
    ],
    'navigation': [
        # English
        'where is', 'find', 'navigate to', 'go to', 'locate', 'how to access',
        # French
        'où est', 'trouver', 'naviguer vers', 'aller à', 'localiser', 'comment accéder',
        # Spanish
        'dónde está', 'encontrar', 'navegar a', 'ir a', 'localizar', 'cómo acceder',
        # Arabic
        'أين', 'البحث عن', 'الانتقال إلى', 'الذهاب إلى', 'كيفية الوصول'
    ]
}


def is_workflow_question(message: str) -> bool:
    """Check if the message is asking about a workflow/how-to."""
    message_lower = message.lower()

    # Check for workflow keywords
    for keyword in WORKFLOW_KEYWORDS:
        if keyword in message_lower:
            return True

    # Check for workflow trigger phrases
    for workflow_id, triggers in WORKFLOW_TRIGGERS.items():
        for trigger in triggers:
            if trigger in message_lower:
                return True

    return False


def find_matching_workflow(message: str, user_role: str):
    """
    Find the best matching workflow for a message.

    Returns:
        Tuple of (workflow, match_score) or (None, 0)
    """
    service = _workflow_service()
    if not service:
        logger.warning("WorkflowDocsService not available")
        return None, 0

    message_lower = message.lower()
    best_match = None
    best_score = 0

    logger.info(f"Finding workflow for message: '{message_lower}' (role: {user_role})")

    # First, check for direct workflow triggers
    for workflow_id, triggers in WORKFLOW_TRIGGERS.items():
        for trigger in triggers:
            if trigger in message_lower:
                logger.info(f"Trigger '{trigger}' matched for workflow '{workflow_id}'")
                workflow = service.get_workflow_by_id(workflow_id)
                if workflow:
                    logger.info(f"Workflow found: {workflow.id} (roles: {workflow.roles})")
                    # Check role access
                    if user_role in workflow.roles or 'all' in workflow.roles or user_role in ['admin', 'system_manager']:
                        score = len(trigger) + 10  # Bonus for direct trigger match
                        if score > best_score:
                            best_match = workflow
                            best_score = score
                            logger.info(f"Workflow matched: {workflow.id} (score: {score})")
                    else:
                        logger.info(f"Role mismatch: user={user_role}, workflow.roles={workflow.roles}")
                else:
                    logger.warning(f"Workflow '{workflow_id}' not found in service")

    # If no direct match, try keyword search
    if not best_match:
        role_filter = None if user_role in ['admin', 'system_manager'] else user_role
        workflows = service.search_workflows(message, role=role_filter)
        if workflows:
            best_match = workflows[0]
            best_score = 5  # Lower score for search match

    return best_match, best_score


# Translated labels for workflow responses
WORKFLOW_LABELS = {
    'en': {
        'prerequisites': 'Prerequisites',
        'steps': 'Steps',
        'fields_to_fill': 'Fields to fill',
        'required': 'required',
        'tips': 'Tips',
        'guide_offer': 'Would you like me to guide you through this?',
        'start_tour': 'Start Interactive Tour'
    },
    'fr': {
        'prerequisites': 'Prérequis',
        'steps': 'Étapes',
        'fields_to_fill': 'Champs à remplir',
        'required': 'obligatoire',
        'tips': 'Conseils',
        'guide_offer': 'Voulez-vous que je vous guide à travers ces étapes?',
        'start_tour': 'Démarrer le Guide Interactif'
    },
    'es': {
        'prerequisites': 'Requisitos Previos',
        'steps': 'Pasos',
        'fields_to_fill': 'Campos a completar',
        'required': 'obligatorio',
        'tips': 'Consejos',
        'guide_offer': '¿Le gustaría que le guíe a través de estos pasos?',
        'start_tour': 'Iniciar Guía Interactiva'
    },
    'ar': {
        'prerequisites': 'المتطلبات المسبقة',
        'steps': 'الخطوات',
        'fields_to_fill': 'الحقول المطلوبة',
        'required': 'مطلوب',
        'tips': 'نصائح',
        'guide_offer': 'هل تريد أن أرشدك خلال هذه الخطوات؟',
        'start_tour': 'بدء الجولة التفاعلية'
    }
}


def generate_workflow_response(workflow, language: str = 'en') -> str:
    """
    Generate a chatbot response from a workflow document.

    Returns HTML-formatted response with tour trigger.
    """
    if not workflow:
        return None

    # Get labels for the requested language
    language = _normalize_language(language)
    labels = WORKFLOW_LABELS.get(language, WORKFLOW_LABELS['en'])

    # Build response with steps and tour offer
    response = f"<strong>{workflow.title}</strong><br><br>"
    response += f"{workflow.description}<br><br>"

    # Add prerequisites if any
    if workflow.prerequisites:
        response += f"<strong>{labels['prerequisites']}:</strong><br>"
        for prereq in workflow.prerequisites:
            response += f"• {prereq}<br>"
        response += "<br>"

    # Add steps
    response += f"<strong>{labels['steps']}:</strong><br>"
    for step in workflow.steps:
        response += f"<strong>{step.step_number}. {step.title}</strong><br>"
        response += f"• {step.help_text}<br>"
        if step.fields:
            response += f"• {labels['fields_to_fill']}:<br>"
            for field in step.fields[:4]:  # Limit to 4 fields
                req = f" ({labels['required']})" if field.get('required') else ""
                response += f"  - {field.get('name', 'Field')}{req}<br>"
        response += "<br>"

    # Add tips (limit to 2)
    if workflow.tips:
        response += f"<strong>{labels['tips']}:</strong><br>"
        for tip in workflow.tips[:2]:
            response += f"• {tip}<br>"
        response += "<br>"

    # Add interactive tour trigger
    # This uses a special format that the frontend will parse
    first_page = workflow.pages[0] if workflow.pages else '/dashboard'
    response += f"<br><strong>{labels['guide_offer']}</strong><br>"
    response += f"<a href='{first_page}#chatbot-tour={workflow.id}' class='chatbot-tour-trigger' data-workflow='{workflow.id}'>"
    response += f"<i class='fas fa-compass'></i> {labels['start_tour']}</a>"

    return response


def try_workflow_response(message: str, user_role: str, language: str = 'en'):
    """
    Try to generate a response from workflow documentation.

    Returns:
        Response string if a workflow matches, None otherwise
    """
    if not is_workflow_question(message):
        return None

    workflow, score = find_matching_workflow(message, user_role)

    if workflow and score > 0:
        logger.info(f"Found matching workflow: {workflow.id} (score: {score}, lang: {language})")

        # Get translated workflow if available
        language = _normalize_language(language)
        service = _workflow_service()
        if service and language != 'en':
            translated = service._get_workflow_translated(workflow.id, language)
            if translated:
                workflow = translated
                logger.info(f"Using translated workflow for {language}")

        return generate_workflow_response(workflow, language)

    return None
