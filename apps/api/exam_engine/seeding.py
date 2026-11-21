"""Siembra idempotente del catálogo de una materia (universidad, materia, módulos, fuentes). Sin preguntas.

Si la materia ya existe, agrega los módulos y fuentes que falten. Un módulo o fuente existente solo se
actualiza (nombre; módulo/páginas/uso de la fuente) si todavía NO tiene reactivos cargados: así se puede
corregir la estructura de una evaluación nueva antes de importar su banco, sin tocar la historia de las
evaluaciones anteriores. Nunca borra nada.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from . import db, models


def seed_catalog(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    with db.tenant_session(None, platform_admin=True) as s:
        uni = s.scalar(select(models.University).where(models.University.code == data["university"]["code"]))
        if uni is None:
            uni = models.University(**data["university"])
            s.add(uni)
            s.flush()
        c = data["course"]
        course = s.scalar(
            select(models.Course).where(models.Course.university_id == uni.id, models.Course.code == c["code"])
        )
        created = course is None
        if created:
            course = models.Course(university_id=uni.id, code=c["code"], name=c["name"], config=c["config"])
            s.add(course)
            s.flush()
        mods = {
            m.module_number: m
            for m in s.scalars(select(models.CourseModule).where(models.CourseModule.course_id == course.id))
        }
        srcs = {
            x.file_name: x
            for x in s.scalars(select(models.CourseSource).where(models.CourseSource.course_id == course.id))
        }
        q_by_module = dict(
            s.execute(
                select(models.QuestionBank.module_number, func.count())
                .where(models.QuestionBank.course_id == course.id)
                .group_by(models.QuestionBank.module_number)
            ).all()
        )
        q_by_source = dict(
            s.execute(
                select(models.QuestionBank.source_id, func.count())
                .where(models.QuestionBank.course_id == course.id)
                .group_by(models.QuestionBank.source_id)
            ).all()
        )
        added_m = added_s = changed = 0
        skipped: list[str] = []
        for m in c.get("modules", []):
            cur = mods.get(m["module_number"])
            if cur is None:
                s.add(models.CourseModule(university_id=uni.id, course_id=course.id, **m))
                added_m += 1
            elif cur.name != m["name"]:
                if q_by_module.get(cur.module_number):
                    skipped.append(f"módulo {cur.module_number}")
                else:
                    cur.name = m["name"]
                    changed += 1
        for src in c.get("sources", []):
            cur = srcs.get(src["file_name"])
            if cur is None:
                s.add(models.CourseSource(university_id=uni.id, course_id=course.id, **src))
                added_s += 1
                continue
            diff = {k: v for k, v in src.items() if k != "file_name" and getattr(cur, k) != v}
            if diff:
                if q_by_source.get(cur.id):
                    skipped.append(src["file_name"])
                else:
                    for k, v in diff.items():
                        setattr(cur, k, v)
                    changed += 1
        new_mods, new_srcs = added_m, added_s
        verb = "creado" if created else ("actualizado" if new_mods or new_srcs or changed else "sin cambios")
        msg = f"{verb}: {uni.code}/{course.code} · +{new_mods} módulos · +{new_srcs} fuentes · {changed} corregidos"
        if skipped:
            msg += " · sin tocar (ya tienen reactivos): " + ", ".join(skipped)
        return msg
