'use strict';
/**
 * routes/faq.js — preguntas frecuentes (contenido estático de ayuda).
 */
const express = require('express');
const router = express.Router();
const { renderPage } = require('../middleware/render');

const PREGUNTAS = [
  [
    '¿Qué es el límite de horas por día?',
    'El máximo de horas que puede acumular una persona en un día, sumando todas las obras y empresas. ' +
      'Por defecto 24 h. Se configura en <strong>Config</strong>. Si se supera, la línea no se guarda y se muestra un error.',
  ],
  [
    '¿Qué pasa al cerrar un mes?',
    'Se genera un <strong>snapshot</strong> que congela: nombres, DNIs, rangos y horas de cada persona. ' +
      'No se puede modificar desde la app. Si necesitas corregir algo, haz backup primero y luego reabre el mes.',
  ],
  [
    '¿Puedo reabrir un mes cerrado?',
    'Sí, con el botón <em>Reabrir</em>. El snapshot anterior <strong>se borra</strong>. ' +
      'Al recalcular puede haber diferencias si se modificaron diarios o maestros. ' +
      'Los CSVs ya exportados <strong>no se actualizan</strong>.',
  ],
  [
    '¿Qué hace el backup y cuándo hacerlo?',
    'Copia <em>toda</em> la base de datos en la carpeta <code>backups/</code>. ' +
      '<strong>Hazlo antes de cerrar un mes, borrar obras/empresas o restaurar otro backup.</strong>',
  ],
  [
    '¿Qué implica restaurar un backup?',
    'Es un <strong>borrón y cuenta nueva</strong>: todos los datos actuales se reemplazan. ' +
      'Los cambios posteriores al backup se pierden. Úsalo solo en caso de error grave.',
  ],
  [
    '¿Por qué las horas se muestran en HH:MM?',
    'Internamente se guardan como decimales (7.5 h) para sumar correctamente. ' +
      'Se muestran como <code>07:30</code> para facilitar la lectura en pantalla y en Excel.',
  ],
  [
    '¿Qué es el arrastre de parte?',
    'El botón <em>Arrastrar de [fecha]</em> copia las personas y asuntos del último diario disponible ' +
      'de esa obra. Las horas se ponen a <strong>0</strong> para que las revises. ' +
      'Si una persona ya está en el parte actual, no se duplica.',
  ],
  [
    '¿Qué son las subcontratas?',
    'En <em>Maestros → Subcontratas</em> defines que la empresa A subcontrata a B. ' +
      'Al generar o cerrar el mensual de A, se incluyen también las horas de trabajadores de B, ' +
      'marcados con ✓ en la columna Sub.',
  ],
  [
    '¿Qué es el rango profesional?',
    'Cada persona tiene un rango (Peón, Oficial 1ª, Capataz…). ' +
      'Al añadir una línea en el diario se usa el rango activo en esa fecha. ' +
      'El historial de rangos se conserva aunque cambie. En el mensual aparece el rango del momento.',
  ],
  [
    '¿Qué son las partidas de obra?',
    'Cada obra puede tener fases (ej. <code>1.1 Movimiento de tierras</code>). ' +
      'Se asignan en las líneas del diario para clasificar el trabajo por fase.',
  ],
  [
    '¿Cómo abrir el CSV en Excel?',
    'Excel → Datos → Obtener datos → Desde texto/CSV → selecciona el fichero. ' +
      'Usa punto y coma (;) como separador. Las columnas de horas son texto <code>HH:MM</code>.',
  ],
  [
    '¿Qué es la meta de horas/día? <span class="badge bg-warning text-dark">v1.2</span>',
    'Es la jornada esperada de una persona. Se calcula así: <strong>meta de la persona</strong> ' +
      '(si tiene una propia) &gt; <strong>meta de su empresa</strong> &gt; <strong>meta de la obra</strong> ' +
      '&gt; 8 h por defecto. Se edita en <em>Config → Metas de horas</em>. No bloquea nada: solo avisa ' +
      '(por ejemplo, en la asignación masiva si asignas menos horas de la meta).',
  ],
  [
    '¿Qué es el desajuste de meta persona/empresa? <span class="badge bg-warning text-dark">v1.2</span>',
    'Si la meta de una persona y la de su empresa difieren más del "umbral de desajuste" configurado, ' +
      'se muestra un aviso al vincular la persona a la empresa y en <em>Config → Metas de horas</em>. ' +
      'Es solo informativo, no bloquea el fichaje diario.',
  ],
  [
    '¿Cómo funcionan los costes por hora? <span class="badge bg-warning text-dark">v1.2</span>',
    'Cada rango puede tener un precio/hora en <em>Maestros → Rangos</em>. Una persona puede tener un ' +
      'precio propio (override) que prevalece sobre el de su rango. Los costes solo se ven en ' +
      '<em>Informes → Costes</em>; nunca se muestran en el diario ni en el mensual operativo, y no se ' +
      'guardan: se recalculan cada vez con los precios vigentes.',
  ],
  [
    '¿Qué es la asignación masiva? <span class="badge bg-warning text-dark">v1.2</span>',
    'Desde un parte diario, el botón <em>Asignación masiva</em> permite dar de alta a varias personas ' +
      'de una misma empresa a la vez, con las mismas horas, partida y asunto. Cada persona se valida ' +
      'individualmente (mes cerrado, límite de horas): las que no cumplan quedan bloqueadas y el resto ' +
      'se crean con normalidad.',
  ],
  [
    '¿Qué significa finalizar una obra? <span class="badge bg-warning text-dark">v1.2</span>',
    'Desde <em>Estado de obra</em> puedes finalizar una obra cuando todos sus mensuales estén cerrados. ' +
      'Una obra finalizada queda congelada: no se pueden crear ni editar partes diarios, no se pueden ' +
      'crear ni reabrir mensuales, y la documentación pasa a solo lectura. Se puede reactivar en ' +
      'cualquier momento, pero los mensuales cerrados siguen cerrados hasta que los reabras a mano.',
  ],
  [
    '¿Dónde se guarda la documentación de una obra? <span class="badge bg-warning text-dark">v1.2</span>',
    'En <em>Documentación</em> (icono de carpeta en la ficha de obra) puedes crear carpetas por partida ' +
      'y subir archivos (planos, fotos, PDFs...). Si borras una partida, sus documentos no se pierden: ' +
      'se archivan automáticamente y siguen siendo descargables desde la sección "Documentación archivada".',
  ],
  [
    '¿Qué se registra en la auditoría? <span class="badge bg-warning text-dark">v1.2</span>',
    'En <em>Estado de obra</em> hay un panel "Actividad administrativa" con el histórico de acciones ' +
      'importantes: cerrar/reactivar obra, cerrar/reabrir mensuales y archivado de documentación al ' +
      'borrar una partida. Si el registro de un evento falla por algún motivo, la acción principal ' +
      '(cerrar el mes, etc.) se completa igualmente: la auditoría nunca bloquea el trabajo.',
  ],
];

router.get('/', (req, res) => {
  renderPage(req, res, 'faq/index', { title: 'Ayuda', active: 'faq', preguntas: PREGUNTAS });
});

module.exports = router;
