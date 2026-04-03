# Editar una plantilla de formulario (Generador de formularios)

Usa esta guía cuando necesites actualizar una plantilla existente (las preguntas y secciones que los puntos focales completarán).

## Antes de comenzar

- Necesitas acceso de **Administrador** con permisos de plantilla.
- Confirma si la plantilla ya está en uso (tiene asignaciones activas).
- Decide qué tipo de cambio necesitas:
  - **Seguro**: correcciones de etiqueta/texto de ayuda, agregar campos opcionales, reordenar secciones.
  - **Riesgoso**: cambiar tipos de campos, cambiar reglas requeridas, eliminar campos (puede romper la consistencia entre países).

## Abrir la plantilla

1. Abre **Panel de administración** → **Gestión de formularios y datos** → **Gestionar plantillas**.
2. Encuentra la plantilla y ábrela.
3. Si el sistema muestra múltiples versiones (borrador/publicado), comienza desde el **último borrador** (o crea una nueva versión borrador si es necesario).

## Ediciones comunes (paso a paso)

### Agregar una nueva sección

1. Haz clic en **Agregar sección**.
2. Dale a la sección un nombre claro (esto se convierte en un elemento de navegación para los puntos focales).
3. Guarda.

### Agregar un nuevo campo

1. Abre la sección donde quieres el campo.
2. Haz clic en **Agregar campo**.
3. Elige el tipo de campo (texto/número/fecha/lista desplegable, etc.).
4. Establece la **etiqueta** (exactamente lo que verán los usuarios).
5. Si está disponible, agrega **texto de ayuda** (una oración corta).
6. Establece **Requerido** solo cuando sea realmente necesario.
7. Guarda.

### Actualizar una etiqueta o texto de ayuda

1. Abre el campo.
2. Cambia la etiqueta/texto de ayuda para que coincida con el significado que quieres.
3. Guarda.

### Reordenar secciones o campos

1. Usa el control de arrastre (o controles de movimiento) para reordenar.
2. Guarda.

## Tipos de campos (qué elegir)

- **Texto**: nombres, notas, explicaciones cortas.
- **Número**: conteos y cantidades. Prefiere número cuando necesites totales o validación.
- **Fecha**: fechas (no texto libre).
- **Lista desplegable / elección única**: cuando las respuestas deben ser consistentes entre países.
- **Selección múltiple**: cuando pueden aplicarse múltiples respuestas.
- **Matriz / tabla** (si está disponible): valores repetidos entre categorías. Usa cuando los usuarios deben ingresar la misma medida para múltiples filas.

## Validación y campos requeridos

- Marca un campo como **requerido** solo cuando debe estar presente para que un envío sea utilizable.
- Si los usuarios a menudo se bloquean en **Enviar**, reduce los campos requeridos o agrega instrucciones más claras.
- Cuando cambies reglas de validación, prueba el impacto con una pequeña asignación primero.

## Vinculación al Banco de indicadores (cuando aplica)

Si tu flujo de trabajo usa el **Banco de indicadores**:

- Vincula un campo a un indicador cuando necesites definiciones estandarizadas y reportes consistentes.
- Mantén la etiqueta del campo fácil de usar, incluso si el nombre del indicador es técnico.
- Evita vincular múltiples preguntas diferentes al mismo indicador a menos que realmente representen la misma medida.

## Publicación y prueba

1. Guarda tus cambios de borrador.
2. Si tu sistema requiere publicación, **publica** la nueva versión.
3. Crea una pequeña asignación de prueba (un país) y complétala tú mismo.
4. Corrige etiquetas confusas y elimina campos requeridos innecesarios.

## Problemas comunes

- **Mis cambios no aparecen para los puntos focales**: la versión de la plantilla puede no estar publicada o la asignación puede estar usando una versión publicada más antigua.
- **Los usuarios no pueden enviar después de mi cambio**: un campo requerido o una nueva validación está bloqueando el envío—prueba el formulario como punto focal.
- **Los datos parecen inconsistentes entre países**: evita cambiar tipos de campos/significado a mitad de la recopilación; crea una nueva plantilla/versión y comunica el cambio.

## Relacionado

- [Crear plantilla de formulario](create-template.md)
- [Crear nueva asignación](create-assignment.md)
- [Gestionar asignaciones](manage-assignments.md)
- [Enviar datos de formulario (Punto focal)](../focal-point/submit-data.md)
- [Generador de formularios (avanzado)](form-builder-advanced.md)
