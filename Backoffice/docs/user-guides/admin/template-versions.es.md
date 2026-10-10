# Versiones de plantilla: borrador, despliegue y reversión

Todo cambio que afecte a cómo se rellena un formulario pasa por una **versión**. Esta guía explica qué ocurre con los datos enviados cuando crea, despliega, revierte o elimina una versión, y qué comprueba el sistema por usted.

## Resumen

- Nunca edita el formulario en vivo mientras la gente lo rellena. Trabaja en un **borrador** y luego lo **despliega**.
- Al desplegar, las respuestas ya enviadas se **trasladan** a los mismos campos de la nueva versión.
- Los campos que elimina **no se borran**. Sus datos permanecen en la versión archivada.
- Si algo falla, puede **revertir** desplegando de nuevo la versión archivada.

## Estados de una versión

| Estado | Significado | Quién la ve |
|---|---|---|
| **Borrador** | Trabajo en curso. Solo puede haber un borrador por plantilla. | Administradores en el Form Builder |
| **Publicada** | La versión en vivo. Exactamente una por plantilla. | Puntos focales que rellenan las asignaciones |
| **Archivada** | Una versión en vivo anterior. Se conservan su estructura y sus datos. | Administradores (se puede volver a desplegar) |

## Crear una nueva versión

1. Abra la plantilla en el Form Builder y pulse **Versions**.
2. Pulse **Add New Version**. El borrador es una copia completa de la versión que estaba viendo: estructura, reglas, variables, traducciones y ajustes.
3. Edite el borrador con libertad. Nada cambia para los puntos focales hasta que despliegue.

Notas:

- Solo puede existir un borrador a la vez. Despliegue o descarte primero el borrador actual.
- Las reglas, condiciones, filtros de lista, campos de «etiqueta de entrada» de las secciones y variables del borrador siguen funcionando: se redirigen a los campos copiados.

## Identidad de los campos: cómo sabe el sistema que dos campos son «el mismo»

Cada campo y cada sección tiene una **clave de identidad** oculta. Una copia conserva la clave del original, de modo que tras el despliegue el sistema sabe que «Número de voluntarios» de la versión 3 es el mismo campo que en la versión 2, aunque se haya renombrado o movido.

- Si **renombra, mueve o reformula** un campo, la identidad se mantiene y los datos lo siguen.
- Si **elimina un campo y añade uno nuevo**, el nuevo tiene una identidad nueva y empieza vacío.
- Las claves nunca se sobrescriben por posición. La posición solo se usa para reparar plantillas antiguas anteriores a las claves de identidad.

## Revisar la correspondencia de campos antes de desplegar

Abra **Versions → Review field mapping** (icono de enlace) en el borrador.

| Etiqueta | Significado | Qué hace el despliegue |
|---|---|---|
| **Linked** (Vinculado) | Misma identidad que un campo en vivo | Los datos se trasladan |
| **Suggested** (Sugerido) | El sistema supuso una coincidencia por posición | Confirme o elija otro campo |
| **New field** (Campo nuevo) | Sin equivalente en vivo | Empieza vacío |
| **Orphaned** (Huérfano) | Campo en vivo sin coincidencia en el borrador | Los datos permanecen en la versión archivada |

### Vincular un campo del borrador con un campo en vivo

Úselo cuando haya sustituido un campo y quiera que sus respuestas lo sigan.

- **No se pueden vincular tipos de campo distintos** (por ejemplo una pregunta y una matriz, o una sección estándar y una repetible). Sus datos se almacenan de forma diferente.
- Si los tipos coinciden pero difiere el **tipo de dato** (por ejemplo número frente a texto) o el **indicador**, se le pide confirmación. Las respuestas existentes se trasladan tal cual, por lo que un campo numérico vinculado a uno de texto puede mostrar valores inesperados.
- Si el campo en vivo ya está vinculado a otro campo del borrador, se le pregunta si desea mover el vínculo. El otro campo del borrador pasa a ser un campo nuevo.
- **Mark as new field** elimina un vínculo para que el campo empiece vacío.

## Desplegar

Pulse **Deploy**. El sistema:

1. Comprueba que cada campo de indicador tenga un indicador válido.
2. Comprueba que dos campos del borrador no compartan identidad (si lo hacen, el despliegue se detiene y no cambia nada).
3. Traslada respuestas, filas repetidas, datos de indicadores dinámicos, documentos subidos y estado de flujo de trabajo de página a los campos y páginas correspondientes de la nueva versión.
4. Redirige las variables de la plantilla que leen un campo.
5. Archiva la versión anterior y publica la nueva.
6. Recalcula las tasas de cumplimentación y vacía la caché de la estructura del formulario.

Si algún paso falla, el despliegue se cancela por completo: la versión anterior sigue en vivo.

### Campos con datos que se eliminan en el borrador

Si campos en vivo con datos enviados no tienen correspondencia en el borrador, debe **reconocerlo**:

- En el Form Builder, el cuadro de confirmación indica cuántos campos se ven afectados. Confirmar despliega.
- En la página de correspondencia de campos, marque la casilla junto a **Deploy**.

No se borra nada. Los datos permanecen en la versión archivada, pero dejan de aparecer en el formulario de entrada y en las exportaciones de la versión en vivo. Si no era su intención, vincule los campos (véase arriba) o vuelva al constructor.

### Mientras se introducen datos

- Un despliegue espera a que termine un guardado en curso, de modo que las respuestas guardadas se trasladen.
- Un punto focal que abrió el formulario **antes** del despliegue y pulsa **Guardar** **después** ve: *«This form was updated while you were working on it. Reload the page…»*. Su guardado se rechaza en lugar de perderse en silencio; tras recargar, vuelve a introducir los cambios no guardados.
- Programe los despliegues grandes fuera de las horas de mayor actividad e indique a los puntos focales que guarden antes de desplegar.

## Revertir

Abra **Versions** y despliegue una versión **archivada**. Las respuestas introducidas desde entonces se trasladan de vuelta y se restauran los campos que un despliegue anterior archivó. La misma confirmación se aplica si campos añadidos después de esa versión contienen datos.

## Descartar un borrador o eliminar una versión

- **Discard draft** elimina el borrador y su estructura. Nunca afecta a la versión en vivo.
- **Delete version** solo está disponible para versiones no publicadas. Queda **bloqueada** mientras haya datos enviados, instancias repetidas, documentos subidos, validaciones de IA o estados de página vinculados a la versión. Archive en lugar de eliminar.
- Eliminar versiones no renumera las demás. Un borrador nuevo siempre toma el siguiente número libre.

## Páginas

Si la plantilla está paginada, una página que ya tiene progreso de flujo de trabajo (por ejemplo «enviada») **no se puede eliminar** de la versión en vivo. Cree un borrador, elimine allí la página y despliéguelo. Las páginas sin progreso se pueden eliminar libremente.

## Duplicar una plantilla

**Duplicate** crea una plantilla independiente a partir de la versión en vivo. Las variables que leen un campo se redirigen a la copia de ese campo, de modo que la nueva plantilla nunca lee datos de la antigua.

## El despliegue se detuvo: qué significan los mensajes

| Mensaje | Causa | Qué hacer |
|---|---|---|
| *The selected version was not found for this template.* | Página obsoleta o enlace erróneo | Recargue el Form Builder |
| *Cannot deploy this version: N indicator item(s) have missing/invalid indicator references.* | Campos de indicador sin indicador | Corrija los campos marcados |
| *N field(s) in the live version hold submitted data but have no match…* | Campos eliminados con datos | Revise la correspondencia y luego confirme |
| *Cannot deploy: N field/section identity key(s) are shared by more than one…* | Dos campos comparten identidad | Pida a un desarrollador que ejecute la auditoría de versiones de plantilla (véase el runbook) |
| *Cannot deploy: N submission row(s) exist on the previous version but no fields could be matched…* | Plantilla antigua sin claves de identidad | Pida a un desarrollador que ejecute el relleno de claves de identidad |
| *Cannot delete this version: N data record(s) are linked…* | Existen datos en esa versión | Mantenga la versión archivada |
| *Cannot remove page …* | La página tiene progreso de flujo de trabajo | Elimínela en un borrador nuevo |

## Buenas prácticas

- Haga **un despliegue por cambio de recopilación** y pruebe antes el borrador con una asignación de un solo país.
- Revise la página de correspondencia de campos cada vez que renombre o reestructure campos.
- Prefiera **renombrar** un campo antes que eliminarlo y volver a crearlo, para que los datos lo sigan.
- Evite cambiar el **tipo de dato** de un campo que ya contiene datos. Añada un campo nuevo.
- No elimine versiones archivadas a las que podría tener que volver.

## Relacionado

- [Editar una plantilla (Form Builder)](edit-template.md)
- [Form Builder (avanzado)](form-builder-advanced.md)
- [Solución de problemas de plantillas y asignaciones](troubleshooting-templates-and-assignments.md)
