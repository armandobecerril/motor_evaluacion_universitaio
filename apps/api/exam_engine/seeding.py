"""Siembra idempotente del catálogo de una materia (universidad, materia, módulos, fuentes). Sin preguntas.

Si la materia ya existe, solo agrega los módulos y fuentes que falten (no modifica ni borra los existentes),
de modo que una evaluación nueva puede sumar módulos a la misma materia.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

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
        have_mods = set(
            s.scalars(select(models.CourseModule.module_number).where(models.CourseModule.course_id == course.id))
        )
        have_srcs = set(
            s.scalars(select(models.CourseSource.file_name).where(models.CourseSource.course_id == course.id))
        )
        new_mods = [m for m in c.get("modules", []) if m["module_number"] not in have_mods]
        new_srcs = [x for x in c.get("sources", []) if x["file_name"] not in have_srcs]
        for m in new_mods:
            s.add(models.CourseModule(university_id=uni.id, course_id=course.id, **m))
        for src in new_srcs:
            s.add(models.CourseSource(university_id=uni.id, course_id=course.id, **src))
        verb = "creado" if created else ("actualizado" if new_mods or new_srcs else "sin cambios")
        return f"{verb}: {uni.code}/{course.code} · +{len(new_mods)} módulos · +{len(new_srcs)} fuentes"
