"""Reporte de calidad del banco: cobertura, grupos conceptuales, similitud, distractores y sustento.

No incluye claves de respuesta ni justificaciones en la salida.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from .bank_format import BankItem, fold

BLOOM_TARGET = {"recordar/comprender": 0.15, "aplicar": 0.25, "analizar": 0.30, "evaluar": 0.30}
MAX_STEM_WORDS_20S = 45
ABSOLUTE_WORDS = {"siempre", "nunca", "todos", "ninguno", "jamas", "unicamente", "solo"}
CATCH_ALL = ("todas las anteriores", "ninguna de las anteriores", "todas las opciones", "ninguna opcion")


@dataclass
class Feasibility:
    module: int
    quota: int
    groups: int
    distinct_concepts: int
    max_selectable: int

    @property
    def ok(self) -> bool:
        return self.max_selectable >= self.quota


@dataclass
class QualityReport:
    totals: dict[str, Any] = field(default_factory=dict)
    per_module: dict[int, dict[str, Any]] = field(default_factory=dict)
    findings: list[tuple[str, str]] = field(default_factory=list)  # (nivel, texto) nivel: BLOQUEANTE|ALTO|MEDIO|INFO
    feasibility: list[Feasibility] = field(default_factory=list)

    def add(self, level: str, text: str) -> None:
        self.findings.append((level, text))

    @property
    def blocking(self) -> bool:
        return any(level == "BLOQUEANTE" for level, _ in self.findings)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-záéíóúñü0-9]+", text.lower())


def _shingles(text: str, k: int = 3) -> set[tuple[str, ...]]:
    w = [fold(x) for x in _words(text)]
    return {tuple(w[i : i + k]) for i in range(max(0, len(w) - k + 1))}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _template(it: BankItem) -> str:
    stem = re.sub(re.escape(it.topic), "<TEMA>", it.stem, flags=re.IGNORECASE)
    return fold(stem.split("?")[0])


def build_report(
    items: list[BankItem],
    *,
    per_module_quota: int = 50,
    max_variants_per_group: int = 1,
    seconds_per_question: int = 20,
    source_pages: dict[str, int] | None = None,
) -> QualityReport:
    rep = QualityReport()
    n = len(items)
    by_module: dict[int, list[BankItem]] = defaultdict(list)
    by_group: dict[str, list[BankItem]] = defaultdict(list)
    for it in items:
        by_module[it.module_number].append(it)
        by_group[it.conceptual_group].append(it)

    # --- grupos y conceptos efectivos (variantes con el mismo conjunto de opciones = mismo reactivo) ---
    cosmetic_groups = 0
    distinct_by_group: dict[str, int] = {}
    for g, its in by_group.items():
        option_sets = {frozenset(fold(t) for t in it.options.values()) for it in its}
        distinct_by_group[g] = len(option_sets)
        if len(its) > 1 and len(option_sets) == 1:
            cosmetic_groups += 1
    rep.totals = {
        "reactivos": n,
        "modulos": len(by_module),
        "grupos_conceptuales": len(by_group),
        "variantes_por_grupo": dict(sorted(Counter(len(v) for v in by_group.values()).items())),
        "grupos_con_variantes_cosmeticas": cosmetic_groups,
        "reactivos_independientes_estimados": sum(distinct_by_group.values()),
    }
    # Núcleo de la respuesta correcta repetido entre variantes de un mismo grupo.
    shared_core = 0
    for its in by_group.values():
        if len(its) > 1:
            cores = [set(fold(w) for w in _words(it.options.get(it.correct_option, ""))) for it in its]
            if len(set.intersection(*cores)) >= 5:
                shared_core += 1
    rep.totals["grupos_con_respuesta_correcta_reutilizada"] = shared_core
    if shared_core:
        rep.add(
            "ALTO",
            f"En {shared_core} de {len(by_group)} grupos la respuesta correcta repite la misma frase central en todas "
            "sus variantes: si un intento incluye dos variantes del mismo grupo, la segunda queda prácticamente "
            "resuelta por la primera.",
        )
    if cosmetic_groups:
        rep.add(
            "ALTO",
            f"{cosmetic_groups} de {len(by_group)} grupos tienen variantes con las MISMAS opciones: responder una "
            "variante revela la respuesta de las demás. Contenido independiente estimado: "
            f"{rep.totals['reactivos_independientes_estimados']} reactivos, no {n}.",
        )

    # --- factibilidad de selección por módulo ---
    for m in sorted(by_module):
        groups = defaultdict(int)
        for it in by_module[m]:
            groups[it.conceptual_group] += 1
        max_sel = sum(min(c, max_variants_per_group) for c in groups.values())
        distinct = sum(distinct_by_group[g] for g in groups)
        rep.feasibility.append(Feasibility(m, per_module_quota, len(groups), distinct, max_sel))
    for f in rep.feasibility:
        if not f.ok:
            rep.add(
                "BLOQUEANTE",
                f"Módulo {f.module}: se piden {f.quota} preguntas pero con máx. {max_variants_per_group} variante(s) "
                f"por grupo solo hay {f.max_selectable} seleccionables ({f.groups} grupos).",
            )

    # --- distribución de claves, Bloom, dificultad ---
    keys = Counter(it.correct_option for it in items)
    rep.totals["distribucion_claves"] = {k: keys.get(k, 0) for k in "ABCD"}
    for k, c in keys.items():
        if n and c / n > 0.35:
            rep.add("MEDIO", f"La opción {k} es la correcta en {c / n:.0%} de los reactivos (sesgo de posición).")
    bloom = Counter(it.bloom for it in items)
    bloom_grouped = {
        "recordar/comprender": bloom.get("recordar", 0) + bloom.get("comprender", 0),
        "aplicar": bloom.get("aplicar", 0),
        "analizar": bloom.get("analizar", 0),
        "evaluar": bloom.get("evaluar", 0) + bloom.get("crear", 0),
    }
    rep.totals["bloom"] = bloom_grouped
    for level, target in BLOOM_TARGET.items():
        actual = bloom_grouped[level] / n if n else 0
        if abs(actual - target) > 0.10:
            rep.add("MEDIO", f"Bloom '{level}': {actual:.0%} vs objetivo {target:.0%}.")
    diff = Counter(it.difficulty for it in items)
    rep.totals["dificultad"] = dict(diff)
    if len(diff) == 1:
        rep.add("MEDIO", f"Todas las preguntas tienen dificultad '{next(iter(diff))}': no hay escala para equilibrar.")

    # --- enunciados: plantillas, pistas, longitud ---
    templates = Counter(_template(it) for it in items)
    rep.totals["plantillas_de_enunciado"] = len(templates)
    if n and len(templates) <= max(10, n // 20):
        rep.add(
            "ALTO",
            f"Solo {len(templates)} plantillas de enunciado para {n} reactivos: los enunciados son genéricos y la "
            "decisión depende casi solo de las opciones.",
        )
    topic_hint = sum(1 for it in items if fold(it.topic) in fold(it.stem))
    if topic_hint:
        rep.add("MEDIO", f"{topic_hint} enunciados nombran explícitamente el tema evaluado (pista directa).")
    lengths = [len(_words(it.stem)) for it in items]
    if lengths:
        rep.totals["palabras_enunciado"] = {
            "min": min(lengths),
            "mediana": statistics.median(lengths),
            "max": max(lengths),
        }
        long_ = sum(1 for x in lengths if x > MAX_STEM_WORDS_20S)
        if long_:
            rep.add("MEDIO", f"{long_} enunciados superan {MAX_STEM_WORDS_20S} palabras.")
        reading = [len(_words(it.stem)) + sum(len(_words(o)) for o in it.options.values()) for it in items]
        med = statistics.median(reading)
        wpm = med / (seconds_per_question / 60)
        rep.totals["palabras_a_leer_por_reactivo"] = {"mediana": med, "max": max(reading)}
        rep.totals["velocidad_lectura_requerida_ppm"] = round(wpm)
        if wpm > 250:
            needed = int(-(-med * 60 // 220))  # segundos para leer a 220 ppm (lectura silenciosa típica)
            rep.add(
                "ALTO",
                f"Cada reactivo exige leer ~{med:.0f} palabras (enunciado + opciones) en {seconds_per_question} s, "
                f"≈{wpm:.0f} palabras/min, por encima de la lectura silenciosa típica (200–250). Solo leer a 220 ppm "
                f"toma ~{needed} s. Acortar enunciados o ampliar el tiempo; pilotear antes de publicar.",
            )

    # --- similitud semántica aproximada entre grupos distintos ---
    shingles = [(it, _shingles(it.stem + " " + " ".join(sorted(it.options.values())))) for it in items]
    near_dupes = 0
    if n <= 2000:
        for (a, sa), (b, sb) in combinations(shingles, 2):
            if a.conceptual_group != b.conceptual_group and _jaccard(sa, sb) >= 0.8:
                near_dupes += 1
    rep.totals["pares_casi_duplicados_entre_grupos"] = near_dupes
    if near_dupes:
        rep.add("ALTO", f"{near_dupes} pares de reactivos casi idénticos pertenecen a grupos conceptuales distintos.")

    # --- distractores ---
    longest_correct = 0
    absolute = 0
    catch_all = 0
    for it in items:
        lens = {k: len(v) for k, v in it.options.items()}
        if (
            lens
            and lens.get(it.correct_option) == max(lens.values())
            and list(lens.values()).count(max(lens.values())) == 1
        ):
            longest_correct += 1
        for k, v in it.options.items():
            fv = fold(v)
            if k != it.correct_option and set(_words(fv)) & ABSOLUTE_WORDS:
                absolute += 1
            if any(c in fv for c in CATCH_ALL):
                catch_all += 1
    rep.totals["correcta_es_la_mas_larga"] = longest_correct
    if n and longest_correct / n > 0.40:
        rep.add(
            "ALTO" if longest_correct / n > 0.6 else "MEDIO",
            f"En {longest_correct / n:.0%} de los reactivos la correcta es la opción más larga (pista).",
        )
    if absolute:
        rep.add("INFO", f"{absolute} distractores usan palabras absolutas (siempre/nunca/solo…), fáciles de descartar.")
    if catch_all:
        rep.add("MEDIO", f"{catch_all} opciones tipo 'todas/ninguna de las anteriores'.")
    rationales = Counter(fold(it.rationale) for it in items)
    repeated = sum(c for c in rationales.values() if c > 1)
    if repeated:
        rep.add("INFO", f"{repeated} reactivos comparten justificación idéntica con otro reactivo.")

    # --- sustento por página ---
    pages = defaultdict(set)
    for it in items:
        if it.source_page is not None:
            pages[it.source_pdf].add(it.source_page)
    coverage = {}
    for pdf, ps in sorted(pages.items()):
        total = (source_pages or {}).get(pdf)
        coverage[pdf] = {"paginas_citadas": len(ps), "paginas_pdf": total}
    rep.totals["cobertura_fuentes"] = coverage
    no_page = sum(1 for it in items if it.source_page is None)
    rep.totals["sin_pagina_citada"] = no_page
    if no_page:
        rep.add(
            "ALTO",
            f"{no_page} reactivos no citan página: el sustento verificable por página queda pendiente "
            "de revisión docente.",
        )
    rep.add(
        "INFO",
        "La página citada (source_page) debe verificarse por el docente: el validador comprueba que exista, no que "
        "sustente el reactivo.",
    )

    # --- por módulo ---
    for m, its in sorted(by_module.items()):
        rep.per_module[m] = {
            "reactivos": len(its),
            "grupos": len({it.conceptual_group for it in its}),
            "claves": dict(sorted(Counter(it.correct_option for it in its).items())),
            "bloom": dict(sorted(Counter(it.bloom for it in its).items())),
            "temas": len({it.topic for it in its}),
        }
    return rep


def render_markdown(rep: QualityReport, title: str, config_note: str) -> str:
    order = {"BLOQUEANTE": 0, "ALTO": 1, "MEDIO": 2, "INFO": 3}
    t = rep.totals
    lines = [f"# Reporte de calidad — {title}", "", config_note, ""]
    verdict = "NO APTO para publicar con esta configuración" if rep.blocking else "Sin bloqueantes de configuración"
    lines += [f"**Veredicto:** {verdict}. Ningún reactivo puede usarse sin aprobación docente.", ""]
    lines += ["## Resumen", "", "| Indicador | Valor |", "|---|---|"]
    for k in (
        "reactivos",
        "modulos",
        "grupos_conceptuales",
        "grupos_con_variantes_cosmeticas",
        "reactivos_independientes_estimados",
        "plantillas_de_enunciado",
        "pares_casi_duplicados_entre_grupos",
        "correcta_es_la_mas_larga",
        "sin_pagina_citada",
        "grupos_con_respuesta_correcta_reutilizada",
        "velocidad_lectura_requerida_ppm",
    ):
        if k in t:
            lines.append(f"| {k.replace('_', ' ')} | {t[k]} |")
    lines += [
        f"| variantes por grupo | {t.get('variantes_por_grupo')} |",
        f"| distribución de claves | {t.get('distribucion_claves')} |",
        f"| Bloom | {t.get('bloom')} |",
        f"| dificultad | {t.get('dificultad')} |",
        f"| palabras por enunciado | {t.get('palabras_enunciado')} |",
        "",
        "## Hallazgos",
        "",
    ]
    for level, text in sorted(rep.findings, key=lambda x: order[x[0]]):
        lines.append(f"- **{level}** — {text}")
    lines += [
        "",
        "## Factibilidad por módulo",
        "",
        "| Módulo | Cuota | Grupos | Seleccionables | ¿Alcanza? |",
        "|---|---|---|---|---|",
    ]
    for f in rep.feasibility:
        lines.append(f"| {f.module} | {f.quota} | {f.groups} | {f.max_selectable} | {'sí' if f.ok else 'NO'} |")
    lines += [
        "",
        "## Por módulo",
        "",
        "| Módulo | Reactivos | Grupos | Temas | Claves | Bloom |",
        "|---|---|---|---|---|---|",
    ]
    for m, d in rep.per_module.items():
        lines.append(f"| {m} | {d['reactivos']} | {d['grupos']} | {d['temas']} | {d['claves']} | {d['bloom']} |")
    lines += ["", "## Cobertura de fuentes", "", "| PDF | Páginas citadas | Páginas del PDF |", "|---|---|---|"]
    for pdf, c in t.get("cobertura_fuentes", {}).items():
        lines.append(f"| {pdf} | {c['paginas_citadas']} | {c['paginas_pdf'] or '?'} |")
    lines.append("")
    return "\n".join(lines)
