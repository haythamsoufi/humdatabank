"""Static page explanations for the in-app chatbot.

Split out of ``helpers`` so prompt assembly and OpenAI integration stay separate
from the long translated copy. Re-exported from ``helpers`` for existing imports.
"""
from app.services.platform.app_settings_service import get_organization_name


def _normalize_language(language):
    from app.services.ai.chat.helpers import normalize_chatbot_language
    return normalize_chatbot_language(language)


def is_page_explanation_request(message, language='en'):
    """Check if the user is asking for a page explanation in any supported language"""
    language = _normalize_language(language)
    explanation_patterns = {
        'en': [
            'explain this page', 'what is this page', 'what does this page do',
            'describe this page', 'what am i looking at', 'page explanation',
            'help with this page', 'what is this', 'page info', 'page details',
            'what should i do', 'what can i do', 'what do i do',
            'how do i use this page', 'how to use this page', 'what actions can i take',
            'what should i do here', 'what can i do here', 'what do i do here',
            'guide me', 'help me', 'show me how', 'where do i start',
            'what are my options', 'available actions', 'next steps'
        ],
        'es': [
            'explica esta página', 'qué es esta página', 'qué hace esta página',
            'describe esta página', 'qué estoy viendo', 'explicación de página',
            'ayuda con esta página', 'qué es esto', 'información de página',
            'qué debo hacer', 'qué puedo hacer', 'qué hago',
            'cómo uso esta página', 'cómo usar esta página', 'qué acciones puedo tomar',
            'guíame', 'ayúdame', 'muéstrame cómo', 'dónde empiezo',
            'cuáles son mis opciones', 'acciones disponibles', 'próximos pasos'
        ],
        'fr': [
            'expliquez cette page', 'qu\'est-ce que cette page', 'que fait cette page',
            'décrivez cette page', 'qu\'est-ce que je regarde', 'explication de page',
            'aide avec cette page', 'qu\'est-ce que c\'est', 'informations sur la page',
            'que dois-je faire', 'que puis-je faire', 'que fais-je',
            'comment utiliser cette page', 'comment utiliser cette page', 'quelles actions puis-je prendre',
            'guidez-moi', 'aidez-moi', 'montrez-moi comment', 'où commencer',
            'quelles sont mes options', 'actions disponibles', 'prochaines étapes'
        ],
        'ar': [
            'اشرح هذه الصفحة', 'ما هذه الصفحة', 'ماذا تفعل هذه الصفحة',
            'صف هذه الصفحة', 'ماذا أرى', 'شرح الصفحة',
            'مساعدة في هذه الصفحة', 'ما هذا', 'معلومات الصفحة',
            'ماذا يجب أن أفعل', 'ماذا يمكنني أن أفعل', 'ماذا أفعل',
            'كيف أستخدم هذه الصفحة', 'كيفية استخدام هذه الصفحة', 'ما الإجراءات التي يمكنني اتخاذها',
            'أرشدني', 'ساعدني', 'أرني كيف', 'من أين أبدأ',
            'ما هي خياراتي', 'الإجراءات المتاحة', 'الخطوات التالية'
        ]
    }

    message_lower = message.lower().strip()
    patterns = explanation_patterns.get(language, explanation_patterns['en'])

    return any(pattern in message_lower for pattern in patterns)

def get_page_explanation(page_context, language='en'):
    """Generate detailed page explanation based on context and language"""
    language = _normalize_language(language)
    if not page_context:
        return None

    page_type = page_context.get('pageData', {}).get('pageType', 'unknown')

    explanations = {
        'en': get_page_explanations_english(),
        'es': get_page_explanations_spanish(),
        'fr': get_page_explanations_french(),
        'ar': get_page_explanations_arabic()
    }

    page_explanations = explanations.get(language, explanations['en'])

    if page_type in page_explanations:
        base_explanation = page_explanations[page_type]

        # Add context-specific information
        context_info = []

        # Add form information
        if 'formFields' in page_context.get('uiElements', {}):
            fields = page_context['uiElements']['formFields']
            if language == 'es':
                context_info.append(f"Esta página contiene {sum(fields.values())} campos de formulario.")
            elif language == 'fr':
                context_info.append(f"Cette page contient {sum(fields.values())} champs de formulaire.")
            elif language == 'ar':
                context_info.append(f"تحتوي هذه الصفحة على {sum(fields.values())} حقل نموذج.")
            else:
                context_info.append(f"This page contains {sum(fields.values())} form fields.")

        # Add table information
        if 'tables' in page_context.get('dataElements', {}):
            table_count = page_context['dataElements']['tables']
            row_count = page_context['dataElements'].get('rowCount', 0)
            if language == 'es':
                context_info.append(f"Hay {table_count} tabla(s) con {row_count} filas de datos.")
            elif language == 'fr':
                context_info.append(f"Il y a {table_count} tableau(x) avec {row_count} lignes de données.")
            elif language == 'ar':
                context_info.append(f"يوجد {table_count} جدول/جداول مع {row_count} صف من البيانات.")
            else:
                context_info.append(f"There are {table_count} table(s) with {row_count} rows of data.")

        if context_info:
            return f"{base_explanation}\n\n{' '.join(context_info)}"

        return base_explanation

    # Generic fallback explanation
    org_name = get_organization_name()
    fallback_explanations = {
        'en': f"This is a page within the {org_name} platform. It appears to be part of the administrative or data management system.",
        'es': f"Esta es una página dentro de la plataforma {org_name}. Parece ser parte del sistema administrativo o de gestión de datos.",
        'fr': f"Ceci est une page de la plateforme {org_name}. Il semble faire partie du système administratif ou de gestion des données.",
        'ar': f"هذه صفحة ضمن منصة {org_name}. يبدو أنها جزء من النظام الإداري أو نظام إدارة البيانات."
    }

    return fallback_explanations.get(language, fallback_explanations['en'])

def get_page_explanations_english():
    """English page explanations"""
    org_name = get_organization_name()
    return {
        'dashboard': f"""**Dashboard - {org_name}**

This is your main dashboard page, your command center for the {org_name} system.

**Primary Purpose:**
- Provides an overview of all platform activities
- Shows key performance indicators (KPIs) and metrics
- Offers quick access to most-used functions
- Displays important alerts and notifications

**Key Features:**
- **Activity Summary**: View of recent system activities
- **Quick Links**: Direct links to common tasks
- **Status Indicators**: System status and alerts
- **Navigation**: Starting point for all platform functions

**Best Practices:**
- Regularly check important notifications
- Use quick links for efficient navigation
- Monitor KPIs for system performance""",

        'user_management': """**User Management - Administrative System**

This page allows you to administer user accounts and permissions within the {org_name} system.

**Main Functionalities:**
- **Account Administration**: Create, edit, and deactivate user accounts
- **Role Management**: Assign roles (Administrator, Focal Point, etc.)
- **Permission Control**: Configure what each user can do
- **Activity Monitoring**: Track user actions and logins

**Available User Roles:**
- **Administrator**: Full system access and management
- **Focal Point**: Can manage specific country/region data
- **User**: Basic access for data entry and viewing

**Security Features:**
- Failed login attempt tracking
- Password policy configuration
- User session management

**Management Tips:**
- Regularly review user permissions
- Monitor suspicious logins
- Keep user information up to date""",

        'template_management': """**Template Management - Form Creation**

Here you can create, modify, and manage form templates for data collection across the organization.

**Core Capabilities:**
- **Form Builder**: Drag-and-drop tools for creating forms
- **Field Library**: Pre-configured field types (text, number, date, etc.)
- **Conditional Logic**: Set up fields that appear based on responses
- **Data Validation**: Establish rules for data entry

**Available Field Types:**
- Text fields (single/multi-line)
- Numeric fields with validation
- Date and time selectors
- Dropdown menus and checkboxes
- File upload fields

**Advanced Features:**
- **Repeatable Sections**: For variable data sets
- **Dynamic Indicators**: Fields that adjust based on context
- **Multi-language Validation**: Support for multiple languages

**Workflow:**
1. Design form structure
2. Configure validation and logic
3. Test the form
4. Deploy to target users""",

        'assignment_management': """**Assignment Management - Task Distribution**

This page manages the distribution and tracking of data form assignments to specific users.

**Primary Functions:**
- **Assignment Creation**: Assign forms to specific users/groups
- **Progress Tracking**: Monitor completion status
- **Deadline Management**: Set and monitor due dates
- **Automated Reminders**: Notification system for pending tasks

**Assignment Statuses:**
- **Pending**: Newly created, awaiting work
- **In Progress**: User has started but not finished
- **Completed**: Submitted and finalized
- **Overdue**: Passed deadline without completion

**Tracking Capabilities:**
- View all assignments by user
- Filter by status, due date, or form type
- Generate completion reports
- Export progress data

**Best Practices:**
- Set realistic deadlines
- Send reminders before due dates
- Regularly review progress
- Provide timely feedback""",

        'country_management': """**Country Management - Geographic Organization**

Manages country information, regions, and geographic data for the {org_name} system.

**Main Features:**
- **Country Profiles**: Detailed information for each country
- **Regional Grouping**: Organize countries by IFRC regions
- **Focal Point Assignment**: Connect users to specific countries
- **Contextual Data**: Population, economy, and other relevant information

**Information Managed:**
- Country names and ISO codes
- Regional affiliations
- National Society contact details
- Demographic and economic information
- Country-specific configurations

**Regional Features:**
- Grouping by IFRC regions (Africa, Americas, Asia-Pacific, Europe, MENA)
- Regional coordinators
- Regional policy settings
- Aggregated regional reports

**Use Cases:**
- Setting up new country operations
- Updating National Society information
- Managing personnel changes
- Generating regional reports""",

        'indicator_bank': """**Indicator Bank - Data Metrics Management**

The Indicator Bank is your central repository for managing and organizing all data collection indicators used in operations.

**Primary Purpose:**
- Standardize indicators across the organization
- Ensure data quality and consistency
- Facilitate data comparison and aggregation
- Provide clear definitions and metadata

**Key Features:**
- **Indicator Library**: Comprehensive repository of all available indicators
- **Categorization**: Organized by sectors, themes, and program types
- **Standardized Definitions**: Each indicator includes clear definitions, units of measurement, and calculation methodology
- **Version Control**: Track changes and updates to indicators

**Organization:**
- **By Sector**: Health, WASH, Food Security, etc.
- **By Type**: Outcome, Output, Impact
- **By Programme**: Emergency, Development, Preparedness
- **By Disaggregation**: Age, Gender, Vulnerability

**Management Capabilities:**
- Add new indicators to the bank
- Edit existing definitions and metadata
- Mark indicators as deprecated
- Link related indicators

**Best Practices:**
- Always use indicators from the bank when available
- Propose new indicators when needed
- Regularly review for updates
- Ensure definitions are clear and measurable""",

        'document_management': """**Document Management - File Storage System**

Central hub for uploading, organizing, and managing documents and files throughout the {org_name} system.

**Core Capabilities:**
- **File Upload**: Upload documents in various formats
- **Organization**: Categorization and tagging of documents
- **Access Control**: Manage who can view/edit documents
- **Version Control**: Track document changes and revisions

**Supported Document Types:**
- PDF and text documents
- Spreadsheets and data files
- Images and graphics
- Presentations
- Form and template files

**Organizational Features:**
- Hierarchical folder structure
- Tagging system
- Search functionality
- Filters by type, date, and author""",

        'analytics': """**Analytics Dashboard - Insights and Reporting**

Comprehensive dashboard for data analysis, reporting, and insights on {org_name} operations.

**Analytics Capabilities:**
- **User Metrics**: User activity and engagement analysis
- **Data Analysis**: Submission trends and data quality
- **System Reports**: Platform performance and usage
- **Custom Dashboards**: Customizable views for different roles

**Report Types:**
- Assignment completion reports
- Data quality analysis
- User engagement metrics
- Time-based trend tracking

**Visualization Features:**
- Interactive charts and graphs
- Export capabilities
- Scheduled reports
- Real-time data alerts""",

        'api_management': """**API Management - Data Access Control**

Manages API keys, usage, and access for external system integrations with the {org_name}.

**Primary Functions:**
- **API Key Management**: Create, rotate, and revoke API keys
- **Usage Tracking**: Monitor API calls and usage quotas
- **Access Control**: Configure permissions for different endpoints
- **API Documentation**: Access to technical documentation

**Security Features:**
- Token-based authentication
- Rate limiting
- API access audit logs
- Granular permission control""",

        'data_entry': """**Data Entry Form - Information Collection**

Interactive form for entering and submitting data to the {org_name} system.

**Form Features:**
- **Real-time Validation**: Immediate data entry verification
- **Auto-save**: Prevent data loss
- **Conditional Logic**: Fields appear based on responses
- **Multi-language Support**: Available in multiple languages

**Field Types:**
- Text and textarea fields
- Numeric fields with formatting
- Date selectors
- Dropdown menus
- Checkboxes and radio buttons
- File uploaders

**Save Functionality:**
- Automatic draft saving
- Validation before submission
- Submission confirmation
- Submission receipts""",

        'publication_management': """**Publication Management - Content Management**

Manages publications, reports, and public content for the IFRC website and communications.

**Content Features:**
- **Publication Creation**: Content authoring tools
- **Media Management**: Image and file uploads
- **Scheduling**: Schedule publications for future dates
- **Approval Workflows**: Review process before publication

**Publication Types:**
- Situation reports
- Success stories
- Technical guides
- Communication materials
- Training resources""",

        'public_assignment_management': """**Public Assignment Management - External Form Links**

Manages public links and access for external form submissions without requiring user accounts.

**Core Capabilities:**
- **Link Generation**: Create unique links for specific forms
- **Access Control**: Configure who can access public forms
- **Submission Tracking**: Monitor submissions from external sources
- **Deadline Management**: Set availability periods for links

**Security Features:**
- Unique, secure links
- Link expiration
- Submission rate limiting
- Submission data verification

**Use Cases:**
- Partner data collection
- Public surveys
- Event registration forms
- Community feedback collection""",

        'account_settings': """**Account Settings - Personal Profile Management**

Manage your personal account information, preferences, and security settings.

**Profile Settings:**
- **Personal Information**: Name, email, title, contact information
- **Language Preferences**: Set preferred interface language
- **Notification Settings**: Choose which notifications to receive
- **Timezone Configuration**: Set local timezone

**Security Settings:**
- **Password Change**: Update login credentials
- **Two-Factor Authentication**: Set up additional security
- **Session Management**: View and manage active sessions
- **Activity Log**: Review recent account activity

**Privacy Settings:**
- Profile visibility control
- Data sharing settings
- Communication preferences"""
    }

def get_page_explanations_spanish():
    """Spanish page explanations"""
    org_name = get_organization_name()
    return {
        'dashboard': f"""**Panel de Control - {org_name}**

Esta es tu página principal del panel de control, tu centro de comando para el sistema de base de datos de la red IFRC.

**Propósito Principal:**
- Proporciona una vista general de todas las actividades de la plataforma
- Muestra estadísticas clave de rendimiento (KPIs) y métricas
- Ofrece acceso rápido a las funciones más utilizadas
- Presenta alertas importantes y notificaciones

**Características Clave:**
- **Resumen de Actividad**: Vista de actividades recientes del sistema
- **Accesos Rápidos**: Enlaces directos a tareas comunes
- **Indicadores de Estado**: Estado del sistema y alertas
- **Navegación**: Punto de partida para todas las funciones de la plataforma

**Mejores Prácticas:**
- Revisa regularmente las notificaciones importantes
- Utiliza los accesos rápidos para navegación eficiente
- Supervisa los KPIs para el rendimiento del sistema""",

        'user_management': """**Gestión de Usuarios - Sistema Administrativo**

Esta página te permite administrar cuentas de usuario y permisos dentro del sistema {org_name}.

**Funcionalidades Principales:**
- **Administración de Cuentas**: Crear, editar y desactivar cuentas de usuario
- **Gestión de Roles**: Asignar roles (Administrador, Punto Focal, etc.)
- **Control de Permisos**: Configurar qué puede hacer cada usuario
- **Supervisión de Actividad**: Rastrear acciones e inicios de sesión de usuarios

**Roles de Usuario Disponibles:**
- **Administrador**: Acceso completo al sistema y gestión
- **Punto Focal**: Puede gestionar datos de país/región específicos
- **Usuario**: Acceso básico para entrada y visualización de datos

**Características de Seguridad:**
- Seguimiento de intentos de inicio de sesión fallidos
- Configuración de políticas de contraseñas
- Gestión de sesiones de usuario

**Consejos de Gestión:**
- Revisa regularmente los permisos de usuario
- Supervisa los inicios de sesión sospechosos
- Mantén actualizada la información de los usuarios""",

        'template_management': """**Gestión de Plantillas - Creación de Formularios**

Aquí puedes crear, modificar y gestionar plantillas de formularios para la recolección de datos en toda la red IFRC.

**Capacidades Principales:**
- **Constructor de Formularios**: Herramientas de arrastrar y soltar para crear formularios
- **Biblioteca de Campos**: Tipos de campo preconfigurados (texto, número, fecha, etc.)
- **Lógica Condicional**: Configurar campos que aparecen según las respuestas
- **Validación de Datos**: Establecer reglas para la entrada de datos

**Tipos de Campo Disponibles:**
- Campos de texto (línea simple/múltiple)
- Campos numéricos con validación
- Selectores de fecha y hora
- Menús desplegables y casillas de verificación
- Campos de carga de archivos

**Características Avanzadas:**
- **Secciones Repetibles**: Para conjuntos de datos variables
- **Indicadores Dinámicos**: Campos que se ajustan según el contexto
- **Validación Multilingual**: Soporte para múltiples idiomas

**Flujo de Trabajo:**
1. Diseñar la estructura del formulario
2. Configurar validación y lógica
3. Probar el formulario
4. Desplegar a usuarios objetivo""",

        'assignment_management': """**Gestión de Asignaciones - Distribución de Tareas**

Esta página gestiona la distribución y seguimiento de asignaciones de formularios de datos a usuarios específicos.

**Funciones Principales:**
- **Creación de Asignaciones**: Asignar formularios a usuarios/grupos específicos
- **Seguimiento de Progreso**: Supervisar el estado de finalización
- **Gestión de Plazos**: Establecer y supervisar fechas límite
- **Recordatorios Automáticos**: Sistema de notificaciones para tareas pendientes

**Estados de Asignación:**
- **Pendiente**: Recién creada, esperando trabajo
- **En Progreso**: Usuario ha comenzado pero no terminado
- **Completada**: Enviada y finalizada
- **Vencida**: Pasó la fecha límite sin completar

**Capacidades de Seguimiento:**
- Ver todas las asignaciones por usuario
- Filtrar por estado, fecha límite o tipo de formulario
- Generar reportes de finalización
- Exportar datos de progreso

**Mejores Prácticas:**
- Establecer fechas límite realistas
- Enviar recordatorios antes de las fechas límite
- Revisar regularmente el progreso
- Proporcionar retroalimentación oportuna""",

        'country_management': """**Gestión de Países - Organización Geográfica**

Gestiona información de países, regiones y datos geográficos para el sistema {org_name}.

**Características Principales:**
- **Perfiles de País**: Información detallada para cada país
- **Agrupación Regional**: Organizar países por regiones IFRC
- **Asignación de Puntos Focales**: Conectar usuarios con países específicos
- **Datos Contextuales**: Población, economía y otra información relevante

**Información Gestionada:**
- Nombres de países y códigos ISO
- Afiliaciones regionales
- Detalles de contacto de Sociedad Nacional
- Información demográfica y económica
- Configuraciones específicas del país

**Características Regionales:**
- Agrupación por regiones IFRC (África, Américas, Asia-Pacífico, Europa, MENA)
- Coordinadores regionales
- Configuraciones de política regional
- Reportes agregados regionales

**Casos de Uso:**
- Configurar nuevas operaciones de país
- Actualizar información de Sociedad Nacional
- Gestionar cambios de personal
- Generar reportes regionales""",

        'indicator_bank': """**Banco de Indicadores - Gestión de Métricas de Datos**

El Banco de Indicadores es tu repositorio central para gestionar y organizar todos los indicadores de recolección de datos utilizados en las operaciones de IFRC.

**Propósito Principal:**
- Estandarizar indicadores en toda la red IFRC
- Asegurar calidad y consistencia de datos
- Facilitar comparación y agregación de datos
- Proporcionar definiciones claras y metadatos

**Características Clave:**
- **Biblioteca de Indicadores**: Repositorio completo de todos los indicadores disponibles
- **Categorización**: Organizado por sectores, temas y tipos de programa
- **Definiciones Estandarizadas**: Cada indicador incluye definiciones claras, unidades de medida y metodología de cálculo
- **Control de Versiones**: Rastreo de cambios y actualizaciones a indicadores

**Organización:**
- **Por Sector**: Salud, WASH, Seguridad Alimentaria, etc.
- **Por Tipo**: Resultado, Producto, Impacto
- **Por Programa**: Emergencia, Desarrollo, Preparación
- **Por Desagregación**: Edad, Género, Vulnerabilidad

**Capacidades de Gestión:**
- Agregar nuevos indicadores al banco
- Editar definiciones e metadatos existentes
- Marcar indicadores como obsoletos
- Vincular indicadores relacionados

**Mejores Prácticas:**
- Siempre usar indicadores del banco cuando estén disponibles
- Proponer nuevos indicadores cuando sea necesario
- Revisar regularmente para actualizaciones
- Asegurar que las definiciones sean claras y medibles""",

        'document_management': """**Gestión de Documentos - Sistema de Almacenamiento**

Centro para cargar, organizar y gestionar documentos y archivos en todo el sistema {org_name}.

**Capacidades Principales:**
- **Carga de Archivos**: Subir documentos de varios formatos
- **Organización**: Categorización y etiquetado de documentos
- **Control de Acceso**: Gestionar quién puede ver/editar documentos
- **Control de Versiones**: Rastrear cambios y revisiones de documentos

**Tipos de Documento Soportados:**
- Documentos PDF y de texto
- Hojas de cálculo y datos
- Imágenes y gráficos
- Presentaciones
- Archivos de formulario y plantilla

**Características Organizacionales:**
- Estructura de carpetas jerárquica
- Sistema de etiquetado
- Funcionalidad de búsqueda
- Filtros por tipo, fecha y autor""",

        'analytics': """**Panel de Análisis - Información y Reportes**

Panel completo para análisis de datos, reportes y información sobre las operaciones del sistema {org_name}.

**Capacidades de Análisis:**
- **Métricas de Usuario**: Análisis de actividad y participación de usuarios
- **Análisis de Datos**: Tendencias de envío y calidad de datos
- **Reportes del Sistema**: Rendimiento y uso de la plataforma
- **Paneles Personalizados**: Vistas personalizables para diferentes roles

**Tipos de Reporte:**
- Reportes de finalización de asignaciones
- Análisis de calidad de datos
- Métricas de participación de usuarios
- Seguimiento de tendencias temporales

**Características de Visualización:**
- Gráficos y tablas interactivos
- Capacidades de exportación
- Reportes programados
- Alertas de datos en tiempo real""",

        'api_management': f"""**Gestión de API - Control de Acceso de Datos**

Gestiona claves de API, uso y acceso para integraciones de sistemas externos con {org_name}.

**Funciones Principales:**
- **Gestión de Claves de API**: Crear, rotar y revocar claves de API
- **Seguimiento de Uso**: Supervisar llamadas de API y cuotas de uso
- **Control de Acceso**: Configurar permisos para diferentes endpoints
- **Documentación de API**: Acceso a documentación técnica

**Características de Seguridad:**
- Autenticación basada en tokens
- Limitación de tasa
- Registro de auditoría de acceso de API
- Control de permisos granular""",

        'data_entry': """**Formulario de Entrada de Datos - Recolección de Información**

Formulario interactivo para entrada y envío de datos al sistema {org_name}.

**Características del Formulario:**
- **Validación en Tiempo Real**: Verificación inmediata de entrada de datos
- **Guardado Automático**: Prevención de pérdida de datos
- **Lógica Condicional**: Los campos aparecen según las respuestas
- **Soporte Multi-idioma**: Disponible en múltiples idiomas

**Tipos de Campo:**
- Campos de texto y área de texto
- Campos numéricos con formato
- Selectores de fecha
- Menús desplegables
- Casillas de verificación y botones de radio
- Cargadores de archivos

**Funcionalidad de Guardado:**
- Guardado de borrador automático
- Validación antes del envío
- Confirmación de envío
- Recibos de envío""",

        'publication_management': """**Gestión de Publicaciones - Gestión de Contenido**

Gestiona publicaciones, reportes y contenido público para el sitio web y comunicaciones de IFRC.

**Características de Contenido:**
- **Creación de Publicaciones**: Herramientas de autoría de contenido
- **Gestión de Medios**: Carga y organización de imágenes
- **Programación**: Programar publicaciones para fechas futuras
- **Flujos de Trabajo de Aprobación**: Proceso de revisión antes de publicación

**Tipos de Publicación:**
- Reportes de situación
- Historias de éxito
- Guías técnicas
- Materiales de comunicación
- Recursos de capacitación""",

        'public_assignment_management': """**Gestión de Asignaciones Públicas - Enlaces de Formulario Público**

Gestiona enlaces públicos y acceso para envíos de formularios externos sin necesidad de cuentas de usuario.

**Capacidades Principales:**
- **Generación de Enlaces**: Crear enlaces únicos para formularios específicos
- **Control de Acceso**: Configurar quién puede acceder a formularios públicos
- **Seguimiento de Envíos**: Supervisar envíos de fuentes externas
- **Gestión de Plazos**: Establecer períodos de disponibilidad para enlaces

**Características de Seguridad:**
- Enlaces únicos y seguros
- Caducidad de enlaces
- Limitación de tasa de envíos
- Verificación de datos de envío

**Casos de Uso:**
- Recolección de datos de socios
- Encuestas públicas
- Formularios de registro de eventos
- Recolección de retroalimentación de la comunidad""",

        'account_settings': """**Configuraciones de Cuenta - Gestión de Perfil Personal**

Gestiona tu información personal de cuenta, preferencias y configuraciones de seguridad.

**Configuraciones de Perfil:**
- **Información Personal**: Nombre, email, cargo, información de contacto
- **Preferencias de Idioma**: Establecer idioma preferido de la interfaz
- **Configuraciones de Notificación**: Elegir qué notificaciones recibir
- **Configuración de Zona Horaria**: Establecer zona horaria local

**Configuraciones de Seguridad:**
- **Cambio de Contraseña**: Actualizar credenciales de inicio de sesión
- **Autenticación de Dos Factores**: Configurar seguridad adicional
- **Gestión de Sesiones**: Ver y gestionar sesiones activas
- **Registro de Actividad**: Revisar actividad reciente de la cuenta

**Configuraciones de Privacidad:**
- Control de visibilidad del perfil
- Configuraciones de compartir datos
- Preferencias de comunicación"""
    }

def get_page_explanations_french():
    """French page explanations"""
    org_name = get_organization_name()
    return {
        'dashboard': f"""**Tableau de Bord - {org_name}**

Ceci est votre page principale du tableau de bord, votre centre de commande pour le système de base de données du réseau IFRC.

**Objectif Principal:**
- Fournit un aperçu de toutes les activités de la plateforme
- Affiche les indicateurs clés de performance (KPI) et les métriques
- Offre un accès rapide aux fonctions les plus utilisées
- Présente les alertes importantes et les notifications

**Caractéristiques Clés:**
- **Résumé d'Activité**: Vue des activités récentes du système
- **Raccourcis**: Liens directs vers les tâches courantes
- **Indicateurs de Statut**: État du système et alertes
- **Navigation**: Point de départ pour toutes les fonctions de la plateforme

**Meilleures Pratiques:**
- Vérifiez régulièrement les notifications importantes
- Utilisez les raccourcis pour une navigation efficace
- Surveillez les KPI pour la performance du système""",

        'user_management': """**Gestion des Utilisateurs - Système Administratif**

Cette page vous permet d'administrer les comptes d'utilisateurs et les permissions dans le système {org_name}.

**Fonctionnalités Principales:**
- **Administration des Comptes**: Créer, modifier et désactiver les comptes d'utilisateurs
- **Gestion des Rôles**: Attribuer des rôles (Administrateur, Point Focal, etc.)
- **Contrôle des Permissions**: Configurer ce que chaque utilisateur peut faire
- **Surveillance de l'Activité**: Suivre les actions et connexions des utilisateurs

**Rôles d'Utilisateur Disponibles:**
- **Administrateur**: Accès complet au système et gestion
- **Point Focal**: Peut gérer des données spécifiques à un pays/région
- **Utilisateur**: Accès de base pour la saisie et la visualisation des données

**Fonctionnalités de Sécurité:**
- Suivi des tentatives de connexion échouées
- Configuration des politiques de mots de passe
- Gestion des sessions d'utilisateur

**Conseils de Gestion:**
- Révisez régulièrement les permissions des utilisateurs
- Surveillez les connexions suspectes
- Maintenez les informations des utilisateurs à jour""",

        'indicator_bank': """**Banque d'Indicateurs - Gestion des Métriques de Données**

La Banque d'Indicateurs est votre référentiel central pour gérer et organiser tous les indicateurs de collecte de données utilisés dans les opérations IFRC.

**Objectif Principal:**
- Standardiser les indicateurs à travers le réseau IFRC
- Assurer la qualité et la cohérence des données
- Faciliter la comparaison et l'agrégation des données
- Fournir des définitions claires et des métadonnées

**Caractéristiques Clés:**
- **Bibliothèque d'Indicateurs**: Référentiel complet de tous les indicateurs disponibles
- **Catégorisation**: Organisé par secteurs, thèmes et types de programmes
- **Définitions Standardisées**: Chaque indicateur inclut des définitions claires, des unités de mesure et une méthodologie de calcul
- **Contrôle de Version**: Suivi des changements et mises à jour des indicateurs

**Organisation:**
- **Par Secteur**: Santé, WASH, Sécurité Alimentaire, etc.
- **Par Type**: Résultat, Produit, Impact
- **Par Programme**: Urgence, Développement, Préparation
- **Par Désagrégation**: Âge, Genre, Vulnérabilité

**Capacités de Gestion:**
- Ajouter de nouveaux indicateurs à la banque
- Modifier les définitions et métadonnées existantes
- Marquer les indicateurs comme obsolètes
- Lier les indicateurs connexes

**Meilleures Pratiques:**
- Toujours utiliser les indicateurs de la banque quand ils sont disponibles
- Proposer de nouveaux indicateurs quand nécessaire
- Réviser régulièrement pour les mises à jour
- S'assurer que les définitions sont claires et mesurables"""
    }

def get_page_explanations_arabic():
    """Arabic page explanations"""
    return {
        'dashboard': """**لوحة التحكم - بنك بيانات شبكة الاتحاد الدولي**

هذه هي صفحة لوحة التحكم الرئيسية الخاصة بك، مركز القيادة لنظام قاعدة بيانات شبكة الاتحاد الدولي.

**الغرض الأساسي:**
- يوفر نظرة عامة على جميع أنشطة المنصة
- يعرض مؤشرات الأداء الرئيسية والمقاييس
- يوفر وصولاً سريعاً للوظائف الأكثر استخداماً
- يعرض التنبيهات والإشعارات المهمة

**الخصائص الرئيسية:**
- **ملخص النشاط**: عرض أنشطة النظام الحديثة
- **الاختصارات**: روابط مباشرة للمهام الشائعة
- **مؤشرات الحالة**: حالة النظام والتنبيهات
- **التنقل**: نقطة البداية لجميع وظائف المنصة

**أفضل الممارسات:**
- راجع الإشعارات المهمة بانتظام
- استخدم الاختصارات للتنقل الفعال
- راقب مؤشرات الأداء الرئيسية لأداء النظام""",

        'user_management': """**إدارة المستخدمين - النظام الإداري**

تتيح لك هذه الصفحة إدارة حسابات المستخدمين والأذونات داخل نظام بنك بيانات شبكة الاتحاد الدولي.

**الوظائف الأساسية:**
- **إدارة الحسابات**: إنشاء وتعديل وإلغاء تفعيل حسابات المستخدمين
- **إدارة الأدوار**: تعيين الأدوار (مدير، نقطة اتصال، إلخ)
- **التحكم في الأذونات**: تكوين ما يمكن لكل مستخدم فعله
- **مراقبة النشاط**: تتبع إجراءات وتسجيلات دخول المستخدمين

**أدوار المستخدم المتاحة:**
- **المدير**: وصول كامل للنظام والإدارة
- **نقطة الاتصال**: يمكنه إدارة بيانات بلد/منطقة محددة
- **المستخدم**: وصول أساسي لإدخال البيانات والعرض

**ميزات الأمان:**
- تتبع محاولات تسجيل الدخول الفاشلة
- تكوين سياسات كلمات المرور
- إدارة جلسات المستخدمين

**نصائح الإدارة:**
- راجع أذونات المستخدمين بانتظام
- راقب تسجيلات الدخول المشبوهة
- حافظ على تحديث معلومات المستخدمين""",

        'indicator_bank': """**بنك المؤشرات - إدارة مقاييس البيانات**

بنك المؤشرات هو مستودعك المركزي لإدارة وتنظيم جميع مؤشرات جمع البيانات المستخدمة في عمليات الاتحاد الدولي.

**الغرض الأساسي:**
- توحيد المؤشرات عبر شبكة الاتحاد الدولي
- ضمان جودة واتساق البيانات
- تسهيل مقارنة وتجميع البيانات
- توفير تعريفات واضحة وبيانات وصفية

**الخصائص الرئيسية:**
- **مكتبة المؤشرات**: مستودع شامل لجميع المؤشرات المتاحة
- **التصنيف**: منظم حسب القطاعات، المواضيع وأنواع البرامج
- **التعريفات المعيارية**: كل مؤشر يتضمن تعريفات واضحة، وحدات قياس ومنهجية حساب
- **التحكم في الإصدار**: تتبع التغييرات والتحديثات للمؤشرات

**التنظيم:**
- **حسب القطاع**: الصحة، المياه والصرف الصحي، الأمن الغذائي، إلخ
- **حسب النوع**: النتيجة، المخرج، التأثير
- **حسب البرنامج**: الطوارئ، التنمية، التأهب
- **حسب التفصيل**: العمر، الجنس، القابلية للتأثر

**قدرات الإدارة:**
- إضافة مؤشرات جديدة للبنك
- تعديل التعريفات والبيانات الوصفية الموجودة
- وضع علامة على المؤشرات كمهجورة
- ربط المؤشرات ذات الصلة

**أفضل الممارسات:**
- استخدم دائماً مؤشرات البنك عندما تكون متاحة
- اقترح مؤشرات جديدة عند الحاجة
- راجع بانتظام للتحديثات
- تأكد من أن التعريفات واضحة وقابلة للقياس"""
    }
