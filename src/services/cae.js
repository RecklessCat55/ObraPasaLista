'use strict';
/**
 * services/cae.js — Coordinación de Actividades Empresariales y Prevención de Riesgos Laborales (PRL).
 *
 * Evalúa caducidades de documentación obligatoria (reconocimientos médicos, cursos PRL 20h,
 * seguros RC, TC2, REA) para operarios y empresas, emitiendo alertas y semáforos para el parte diario.
 */

const TIPOS_DOC_PERSONA = {
  reconocimiento_medico: 'Reconocimiento Médico (Vigilancia Salud)',
  curso_prl: 'Formación PRL (20h / Oficio)',
  dni_nie: 'DNI / NIE / Permiso de Trabajo',
  alta_seguridad_social: 'Alta en Seg. Social (ITA / IDC)',
  otro: 'Otro documento',
};

const TIPOS_DOC_EMPRESA = {
  tc2: 'RLC / RNT (Seguridad Social - TC2)',
  seguro_rc: 'Póliza Seguro Responsabilidad Civil',
  rea: 'Inscripción en el REA',
  corriente_tgss: 'Certificado Corriente TGSS',
  corriente_aeat: 'Certificado Corriente AEAT',
  plan_seguridad: 'Plan de Seguridad / Adhesión',
  otro: 'Otro documento',
};

/**
 * Añade días a una fecha ISO (YYYY-MM-DD).
 */
function sumarDias(fechaStr, dias) {
  const d = new Date(fechaStr);
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

/**
 * Fecha actual en formato YYYY-MM-DD local.
 */
function hoyIso() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * Evalúa el estado documental de un trabajador respecto a una fecha de referencia.
 * @param {import('better-sqlite3').Database} conn
 * @param {number} idPersona
 * @param {string} [fechaRef] YYYY-MM-DD (por defecto hoy)
 * @returns {{ estado: 'ok'|'aviso'|'caducado'|'sin_docs', badgeClass: string, icono: string, titulo: string, alertas: Array<{ tipo: string, titulo: string, caducidad: string|null, nivel: 'danger'|'warning'|'secondary', mensaje: string }> }}
 */
function evaluarDocPersona(conn, idPersona, fechaRef) {
  const fecha = fechaRef || hoyIso();
  const umbralAviso = sumarDias(fecha, 15);

  const docs = conn
    .prepare('SELECT * FROM documentacion_persona WHERE id_persona=? ORDER BY fecha_caducidad ASC')
    .all(idPersona);

  if (!docs.length) {
    return {
      estado: 'sin_docs',
      badgeClass: 'bg-secondary',
      icono: 'bi-file-earmark-x',
      titulo: 'Sin documentación PRL registrada',
      alertas: [
        {
          tipo: 'sin_docs',
          titulo: 'Documentación pendiente',
          caducidad: null,
          nivel: 'secondary',
          mensaje: 'El trabajador no tiene ningún documento registrado en el sistema.',
        },
      ],
    };
  }

  const alertas = [];
  let tieneCaducado = false;
  let tieneAviso = false;

  for (const doc of docs) {
    const nombreTipo = TIPOS_DOC_PERSONA[doc.tipo_doc] || doc.descripcion || doc.tipo_doc;

    if (doc.estado === 'caducado' || (doc.fecha_caducidad && doc.fecha_caducidad < fecha)) {
      tieneCaducado = true;
      alertas.push({
        tipo: doc.tipo_doc,
        titulo: nombreTipo,
        caducidad: doc.fecha_caducidad,
        nivel: 'danger',
        mensaje: `${nombreTipo} caducado el ${doc.fecha_caducidad || 'fecha vencida'}.`,
      });
    } else if (doc.fecha_caducidad && doc.fecha_caducidad <= umbralAviso) {
      tieneAviso = true;
      alertas.push({
        tipo: doc.tipo_doc,
        titulo: nombreTipo,
        caducidad: doc.fecha_caducidad,
        nivel: 'warning',
        mensaje: `${nombreTipo} caduca en menos de 15 días (${doc.fecha_caducidad}).`,
      });
    }
  }

  if (tieneCaducado) {
    return {
      estado: 'caducado',
      badgeClass: 'bg-danger',
      icono: 'bi-shield-fill-x',
      titulo: `${alertas.filter((a) => a.nivel === 'danger').length} documento(s) caducado(s)`,
      alertas,
    };
  }

  if (tieneAviso) {
    return {
      estado: 'aviso',
      badgeClass: 'bg-warning text-dark',
      icono: 'bi-shield-fill-exclamation',
      titulo: `${alertas.filter((a) => a.nivel === 'warning').length} documento(s) próximo(s) a caducar`,
      alertas,
    };
  }

  return {
    estado: 'ok',
    badgeClass: 'bg-success',
    icono: 'bi-shield-fill-check',
    titulo: 'Documentación PRL al día',
    alertas: [],
  };
}

/**
 * Evalúa el estado documental de una empresa respecto a una fecha de referencia.
 * @param {import('better-sqlite3').Database} conn
 * @param {number} idEmpresa
 * @param {string} [fechaRef]
 */
function evaluarDocEmpresa(conn, idEmpresa, fechaRef) {
  const fecha = fechaRef || hoyIso();
  const umbralAviso = sumarDias(fecha, 15);

  const docs = conn
    .prepare('SELECT * FROM documentacion_empresa WHERE id_empresa=? ORDER BY fecha_caducidad ASC')
    .all(idEmpresa);

  if (!docs.length) {
    return {
      estado: 'sin_docs',
      badgeClass: 'bg-secondary',
      icono: 'bi-building-slash',
      titulo: 'Sin documentación de empresa registrada',
      alertas: [
        {
          tipo: 'sin_docs',
          titulo: 'Documentación empresa pendiente',
          caducidad: null,
          nivel: 'secondary',
          mensaje: 'La empresa no tiene TC2 o seguros registrados.',
        },
      ],
    };
  }

  const alertas = [];
  let tieneCaducado = false;
  let tieneAviso = false;

  for (const doc of docs) {
    const nombreTipo = TIPOS_DOC_EMPRESA[doc.tipo_doc] || doc.descripcion || doc.tipo_doc;

    if (doc.estado === 'caducado' || (doc.fecha_caducidad && doc.fecha_caducidad < fecha)) {
      tieneCaducado = true;
      alertas.push({
        tipo: doc.tipo_doc,
        titulo: nombreTipo,
        caducidad: doc.fecha_caducidad,
        nivel: 'danger',
        mensaje: `${nombreTipo} caducado el ${doc.fecha_caducidad || 'fecha vencida'}.`,
      });
    } else if (doc.fecha_caducidad && doc.fecha_caducidad <= umbralAviso) {
      tieneAviso = true;
      alertas.push({
        tipo: doc.tipo_doc,
        titulo: nombreTipo,
        caducidad: doc.fecha_caducidad,
        nivel: 'warning',
        mensaje: `${nombreTipo} caduca próximo (${doc.fecha_caducidad}).`,
      });
    }
  }

  if (tieneCaducado) {
    return {
      estado: 'caducado',
      badgeClass: 'bg-danger',
      icono: 'bi-shield-fill-x',
      titulo: 'Empresa con documentación caducada',
      alertas,
    };
  }

  if (tieneAviso) {
    return {
      estado: 'aviso',
      badgeClass: 'bg-warning text-dark',
      icono: 'bi-shield-fill-exclamation',
      titulo: 'Empresa con documentación próxima a vencer',
      alertas,
    };
  }

  return {
    estado: 'ok',
    badgeClass: 'bg-success',
    icono: 'bi-shield-fill-check',
    titulo: 'Documentación de empresa al día',
    alertas: [],
  };
}

/**
 * Obtiene el mapa de alertas CAE para un parte diario específico.
 * @param {import('better-sqlite3').Database} conn
 * @param {number} idDiario
 */
function obtenerSemaforoDiario(conn, idDiario) {
  const diario = conn.prepare('SELECT id_diario, fecha FROM diario WHERE id_diario=?').get(idDiario);
  if (!diario) return { personas: {}, empresas: {} };

  const lineas = conn
    .prepare('SELECT DISTINCT id_persona, id_empresa FROM diario_linea WHERE id_diario=?')
    .all(idDiario);

  const personas = {};
  const empresas = {};

  for (const l of lineas) {
    if (!personas[l.id_persona]) {
      personas[l.id_persona] = evaluarDocPersona(conn, l.id_persona, diario.fecha);
    }
    if (l.id_empresa && !empresas[l.id_empresa]) {
      empresas[l.id_empresa] = evaluarDocEmpresa(conn, l.id_empresa, diario.fecha);
    }
  }

  return { personas, empresas };
}

module.exports = {
  TIPOS_DOC_PERSONA,
  TIPOS_DOC_EMPRESA,
  evaluarDocPersona,
  evaluarDocEmpresa,
  obtenerSemaforoDiario,
  hoyIso,
  sumarDias,
};
