'use strict';
/**
 * services/fechas.js — helpers de fecha y formato compartidos.
 *
 * Equivalente a services/fechas.py. Se mantienen sin dependencias de otros
 * módulos de la app para evitar imports circulares (igual que en la
 * version Python).
 *
 * Nota de diseño: en Python las fechas se normalizan a `datetime.date`.
 * En JS no tenemos un tipo "solo fecha" nativo, así que aquí una fecha
 * "normalizada" es simplemente el string 'YYYY-MM-DD' (formato con el que
 * trabaja SQLite y el resto de la app). `nf()` se mantiene por paridad de
 * nombres pero devuelve ese mismo string.
 */

/** Normaliza cualquier entrada de fecha (Date | string) a 'YYYY-MM-DD'. */
function nf(f) {
  if (f instanceof Date) {
    // Componentes LOCALES (no toISOString, que es UTC): equivalente a
    // datetime.now()/date.today() de Python, que usan la hora local del
    // servidor. Usar UTC aquí desplazaría "hoy" un día en muchas zonas
    // horarias durante parte del día.
    const y = f.getFullYear();
    const mo = String(f.getMonth() + 1).padStart(2, '0');
    const d = String(f.getDate()).padStart(2, '0');
    return `${y}-${mo}-${d}`;
  }
  if (typeof f === 'string') {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(f);
    if (!m) {
      throw new TypeError(`Fecha con formato no soportado: ${f}`);
    }
    const [, yStr, moStr, dStr] = m;
    const y = Number(yStr);
    const mo = Number(moStr);
    const d = Number(dStr);
    // Valida que sea una fecha de calendario real (equivalente a que
    // datetime.strptime(..., '%Y-%m-%d') lance ValueError con "2026-13-45"
    // o "2026-02-30"): reconstruimos la fecha y comprobamos que coincide.
    const dt = new Date(Date.UTC(y, mo - 1, d));
    if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) {
      throw new TypeError(`Fecha con formato no soportado: ${f}`);
    }
    return f.slice(0, 10);
  }
  throw new TypeError(`Tipo de fecha no soportado: ${typeof f}`);
}

/** -> 'YYYY-MM-DD' */
function fs(f) {
  return nf(f);
}

/** -> 'YYYY-MM' */
function mes(f) {
  return nf(f).slice(0, 7);
}

/** -> entero 1..31 */
function dia(f) {
  return parseInt(nf(f).slice(8, 10), 10);
}

/** Horas decimales -> 'HH:MM' */
function hhmm(h) {
  if (h === null || h === undefined) return '--';
  let hi = Math.trunc(h);
  let m = Math.round((h - hi) * 60);
  if (m === 60) {
    hi += 1;
    m = 0;
  }
  return `${String(hi).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** Normaliza texto: sin acentos, mayúsculas, separado por '_'. */
function norm(s) {
  const sinAcentos = s
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '');
  return sinAcentos
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/** Hoy como 'YYYY-MM-DD' (hora local del servidor). */
function hoyStr() {
  return nf(new Date());
}

module.exports = { nf, fs, mes, dia, hhmm, norm, hoyStr };
