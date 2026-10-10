"""Reporte de calidad (funciones puras, sin BD)."""

from __future__ import annotations

import json

from exam_engine.services.bank_format import parse_bank
from exam_engine.services.quality import build_report, render_markdown

from .conftest import make_bank


def _items(bank: dict):
    parsed = parse_bank(json.dumps(bank).encode(), "b.json")
    assert not parsed.errors, parsed.errors
    return parsed.items


def test_feasibility_blocks_when_groups_insufficient():
    items = _items(make_bank("UDL", groups_per_module=3, variants=4))
    rep = build_report(items, per_module_quota=5, max_variants_per_group=1)
    assert rep.blocking
    assert all(f.max_selectable == 3 and not f.ok for f in rep.feasibility)
    rep2 = build_report(items, per_module_quota=5, max_variants_per_group=2)
    assert not rep2.blocking and all(f.max_selectable == 6 for f in rep2.feasibility)


def test_detects_cosmetic_variants_and_reused_correct_answer():
    bank = make_bank("UDL", groups_per_module=2, variants=3)
    for q in bank["questions"]:
        g = q["concept_id"]
        q["options"] = [{"id": c, "text": f"Alternativa {c} del concepto {g}"} for c in "ABCD"]
    rep = build_report(_items(bank), per_module_quota=1, max_variants_per_group=1)
    assert rep.totals["grupos_con_variantes_cosmeticas"] == 8
    assert rep.totals["reactivos_independientes_estimados"] == 8
    assert any("MISMAS opciones" in t for _, t in rep.findings)


def test_reading_load_flagged_for_long_items():
    bank = make_bank("UDL", groups_per_module=1, variants=1)
    for q in bank["questions"]:
        q["stem"] = " ".join(["palabra"] * 80) + " ¿Qué conviene?"
    rep = build_report(_items(bank), per_module_quota=1, max_variants_per_group=1, seconds_per_question=20)
    assert rep.totals["velocidad_lectura_requerida_ppm"] > 250
    assert any(level == "ALTO" and "palabras/min" in t for level, t in rep.findings)


def test_markdown_has_no_answer_keys_or_rationales():
    bank = make_bank("UDL")
    md = render_markdown(build_report(_items(bank)), "SIAF", "nota")
    assert "Justificación" not in md and "correct_option" not in md
    assert "Opción A del caso" not in md


def test_csv_and_json_parse_equivalently():
    bank = make_bank("UDL", groups_per_module=1, variants=1)
    header = "id,universidad,materia,examen,module,topic,bloom,difficulty,stem,A,B,C,D,correct_option_id,rationale,source_pdf,source_page,conceptual_group,variant,status"
    rows = [header]
    for q in bank["questions"]:
        o = {x["id"]: x["text"] for x in q["options"]}
        rows.append(
            ",".join(
                json.dumps(str(v), ensure_ascii=False)
                for v in [
                    q["id"],
                    q["universidad"],
                    q["materia"],
                    q["examen"],
                    q["module"],
                    q["topic"],
                    q["bloom"],
                    q["difficulty"],
                    q["stem"],
                    o["A"],
                    o["B"],
                    o["C"],
                    o["D"],
                    q["correct_option_id"],
                    q["rationale"],
                    q["source_pdf"],
                    "",
                    q["concept_id"],
                    1,
                    "draft",
                ]
            )
        )
    from_csv = parse_bank(("﻿" + "\n".join(rows)).encode(), "b.csv")
    from_json = parse_bank(json.dumps(bank).encode(), "b.json")
    assert not from_csv.errors, from_csv.errors[:3]

    def key(i):
        return (i.external_id, i.module_number, i.stem, i.options, i.correct_option, i.conceptual_group, i.source_page)

    assert [key(i) for i in from_csv.items] == [key(i) for i in from_json.items]
