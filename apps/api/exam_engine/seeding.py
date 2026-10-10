"""Siembra idempotente del catálogo de una materia (universidad, materia, módulos, fuentes). Sin preguntas."""

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
        existing = s.scalar(
            select(models.Course).where(models.Course.university_id == uni.id, models.Course.code == c["code"])
        )
        if existing is not None:
            return f"sin cambios: {uni.code}/{existing.code} ya existe"
        course = models.Course(university_id=uni.id, code=c["code"], name=c["name"], config=c["config"])
        s.add(course)
        s.flush()
        for m in c["modules"]:
            s.add(models.CourseModule(university_id=uni.id, course_id=course.id, **m))
        for src in c["sources"]:
            s.add(models.CourseSource(university_id=uni.id, course_id=course.id, **src))
        return f"creado: {uni.code}/{course.code} con {len(c['modules'])} módulos y {len(c['sources'])} fuentes"
