# Documentos de respaldo (administrador)

Usa esta guía para entender cómo los documentos de respaldo se relacionan con las asignaciones (por ejemplo: archivos de evidencia, reportes o adjuntos).

## Qué son los documentos de respaldo

Los documentos de respaldo son archivos adjuntos a un envío de asignación para proporcionar:

- documentos de evidencia o fuente
- reportes de contexto
- hojas de cálculo usadas para calcular valores

## Qué requerir (manténlo mínimo)

Si decides requerir documentos:
- Requiere el conjunto mínimo necesario para validar el envío.
- Sé explícito: qué archivo, qué formato y qué convención de nomenclatura.

Ejemplo de texto de requisito:
- "Sube un PDF con la fuente oficial para los totales reportados (nombrado `Country_Period_Source.pdf`)."

## Dónde encontrar documentos

Dependiendo de tu configuración, puedes encontrar documentos:

- dentro de la vista de detalles de una asignación, o
- en un área "Documentos" para la asignación/envío

## Revisar documentos

Al revisar un envío:

1. Abre el envío.
2. Verifica que existan documentos adjuntos cuando tu proceso lo requiera.
3. Confirma que el documento coincide con los valores reportados (el muestreo está bien si el volumen es alto).

## Manejo de datos sensibles (importante)

- Evita solicitar documentos con identificadores personales a menos que sea explícitamente requerido y aprobado.
- Si se requieren documentos sensibles, acuerda:
  - quién puede acceder a ellos
  - dónde pueden ser exportados/compartidos
  - cuánto tiempo se conservan

## Buenas prácticas

- Acuerda convenciones de nomenclatura (ejemplo: `Country_Period_Source.pdf`).
- Prefiere un pequeño conjunto de documentos requeridos en lugar de muchos archivos opcionales.
- Evita subir datos personales sensibles a menos que sea explícitamente requerido y aprobado.

## Problemas comunes

- **Un usuario no puede subir documentos**: confirma que tienen un rol que permite la carga de documentos (por ejemplo `assignment_documents_uploader` o `assignment_editor_submitter`).
- **Faltan documentos**: aclara si los documentos son requeridos para esa asignación y comunica las expectativas a los puntos focales.

## Relacionado

- [Recetas de roles](role-recipes.md)
- [Revisar y aprobar envíos](review-approve-submissions.md)
- [Manejo de datos y privacidad](../common/data-handling-and-privacy.md)
