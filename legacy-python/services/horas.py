# -*- coding: utf-8 -*-
"""
services/horas.py — validaciones de negocio sobre horas y meses.

Extraído de app.py (v1.1) según el punto 2.2 del documento de cambios v1.2.
Cada función recibe la conexión `db` (sqlite3.Connection con row_factory=Row)
como parámetro explícito en lugar de leerla de un contexto Flask, para que
este módulo no dependa de Flask ni de app.py.

Los mensajes de error están pensados para mostrarse directamente al usuario
final (jefe de obra), no jerga de base de datos.
"""
from .fechas import fs, mes, hhmm


def get_lim(db):
    """Límite de horas/día configurado globalmente."""
    r = db.execute('SELECT limite_horas_dia FROM config WHERE id_config=1').fetchone()
    return r['limite_horas_dia'] if r else 24.0


def chk_horas(id_persona, fecha, h_new, db, excl=None):
    """
    Valida que una persona no supere el límite de horas/día al sumar `h_new`
    en `fecha` (contando todas las obras y empresas). Lanza ValueError con un
    mensaje de negocio si se supera.
    `excl` permite excluir una línea concreta (id_dl) al editar.
    """
    lim = get_lim(db)
    q = ("SELECT COALESCE(SUM(dl.horas),0) t FROM diario_linea dl "
         "JOIN diario d ON dl.id_diario=d.id_diario WHERE dl.id_persona=? AND d.fecha=?")
    p = [id_persona, fs(fecha)]
    if excl:
        q += ' AND dl.id_dl!=?'
        p.append(excl)
    tot = db.execute(q, p).fetchone()['t']
    if tot + h_new > lim:
        pr = db.execute("SELECT nombre||' '||apellido1 n FROM persona WHERE id_persona=?", [id_persona]).fetchone()
        raise ValueError(f"{pr['n'] if pr else '?'} ya acumula {hhmm(tot)} ese día. "
                         f"Añadir {hhmm(h_new)} supera el límite de {hhmm(lim)} h/día.")


def chk_mes_cerrado(id_obra, id_empresa, fecha, db):
    """Lanza ValueError si el mensual de esa obra/empresa/mes está cerrado."""
    m = db.execute(
        "SELECT m.estado, o.nombre ob, e.nombre em FROM mensual m "
        "JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa "
        "WHERE m.id_obra=? AND m.id_empresa=? AND m.mes=?",
        [id_obra, id_empresa, mes(fecha)]).fetchone()
    if m and m['estado'] == 'cerrado':
        raise ValueError(f"Mes {mes(fecha)} para '{m['ob']}'/'{m['em']}' está CERRADO.")


def get_rango_activo(id_persona, fecha, db):
    """Devuelve el id_rango activo de una persona en una fecha dada."""
    f = fs(fecha)
    r = db.execute(
        "SELECT id_rango FROM persona_rango "
        "WHERE id_persona=? AND fecha_inicio<=? AND (fecha_fin IS NULL OR fecha_fin>=?) "
        "ORDER BY fecha_inicio DESC LIMIT 1", [id_persona, f, f]).fetchone()
    if r:
        return r['id_rango']
    se = db.execute("SELECT id_rango FROM rango WHERE codigo='SIN_ESPECIFICAR'").fetchone()
    return se['id_rango'] if se else None
