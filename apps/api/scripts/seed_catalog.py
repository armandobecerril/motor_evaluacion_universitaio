"""Siembra el catálogo de una materia (universidad, materia, módulos, fuentes) desde un JSON.

NO siembra preguntas ni alumnos. Idempotente: si la materia ya existe, no hace nada.
Uso:
    python -m scripts.seed_catalog seeds/siaf_catalog.json
Requiere DATABASE_URL (rol exam_app). Corre como platform_admin (crea la universidad si no existe).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from exam_engine import db, models


def seed(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    with db.tenant_session(None, platform_admin=True) as s:
        inst = s.scalar(select(models.Institution).where(models.Institution.code == data["institution"]["code"]))
        if inst is None:
            inst = models.Institution(**data["institution"])
            s.add(inst)
            s.flush()
        subj_data = data["subject"]
        existing = s.scalar(
            select(models.Subject).where(
                models.Subject.institution_id == inst.id, models.Subject.code == subj_data["code"]
            )
        )
        if existing is not None:
            return f"sin cambios: {inst.code}/{existing.code} ya existe"
        subj = models.Subject(
            institution_id=inst.id, code=subj_data["code"], name=subj_data["name"], config=subj_data["config"]
        )
        s.add(subj)
        s.flush()
        modules: dict[int, models.SubjectModule] = {}
        for m in subj_data["modules"]:
            mod = models.SubjectModule(institution_id=inst.id, subject_id=subj.id, **m)
            s.add(mod)
            modules[m["module_number"]] = mod
        s.flush()
        for src in subj_data["sources"]:
            module_number = src.pop("module_number", None)
            s.add(
                models.SubjectSource(
                    institution_id=inst.id,
                    subject_id=subj.id,
                    module_id=modules[module_number].id if module_number else None,
                    **src,
                )
            )
        return f"creado: {inst.code}/{subj.code} con {len(modules)} módulos y {len(subj_data['sources'])} fuentes"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: python -m scripts.seed_catalog <archivo.json>")
    print(seed(Path(sys.argv[1])))
