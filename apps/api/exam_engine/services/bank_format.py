"""Lectura y validación del banco maestro (formato UDL: JSON con ``metadata`` + ``questions``, o CSV).

Funciones puras (sin BD) para poder validar en seco y probar sin infraestructura.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

OPTION_CODES = ("A", "B", "C", "D")

BLOOM_MAP = {
    "recordar": "recordar",
    "comprender": "comprender",
    "entender": "comprender",
    "aplicar": "aplicar",
    "analizar": "analizar",
    "evaluar": "evaluar",
    "crear": "crear",
}
DIFFICULTY_MAP = {
    "baja": "baja",
    "basica": "baja",
    "facil": "baja",
    "intermedia": "intermedia",
    "media": "intermedia",
    "alta": "alta",
    "avanzada": "alta",
    "dificil": "alta",
}
IMPORTABLE_STATUS = {"draft", "reviewed"}


def fold(text: str) -> str:
    """Minúsculas sin acentos, para comparar textos institucionales y vocabularios."""
    norm = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in norm if not unicodedata.combining(c))


@dataclass
class BankItem:
    external_id: str
    universidad: str
    materia: str
    examen: str
    module_number: int
    topic: str
    bloom: str
    difficulty: str
    stem: str
    options: dict[str, str]
    correct_option: str
    rationale: str
    source_pdf: str
    source_page: int | None
    conceptual_group: str
    variant: int
    status_in_file: str
    case_type: str | None = None

    def checksum(self) -> str:
        canonical = json.dumps(
            {
                "module": self.module_number,
                "topic": self.topic,
                "bloom": self.bloom,
                "difficulty": self.difficulty,
                "stem": self.stem,
                "options": self.options,
                "correct": self.correct_option,
                "rationale": self.rationale,
                "source": [self.source_pdf, self.source_page],
                "group": self.conceptual_group,
                "variant": self.variant,
                "case_type": self.case_type,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class ParsedBank:
    metadata: dict[str, Any]
    items: list[BankItem]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def bank_code(self) -> str:
        return str(self.metadata.get("id") or "").strip()


class BankFormatError(ValueError):
    pass


# ------------------------------------------------------------------ lectura ---


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BankFormatError("El archivo debe estar en UTF-8.") from exc


def _rows_from_json(data: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        doc = json.loads(_decode(data))
    except json.JSONDecodeError as exc:
        raise BankFormatError(f"JSON inválido (línea {exc.lineno}): {exc.msg}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("questions"), list):
        raise BankFormatError("El JSON debe ser un objeto con 'metadata' y 'questions' (lista).")
    meta = doc.get("metadata") or {}
    if not isinstance(meta, dict):
        raise BankFormatError("'metadata' debe ser un objeto.")
    return meta, doc["questions"]


def _rows_from_csv(data: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reader = csv.DictReader(io.StringIO(_decode(data)))
    required = {"id", "module", "stem", "A", "B", "C", "D", "correct_option_id", "conceptual_group"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise BankFormatError(f"Faltan columnas en el CSV: {', '.join(sorted(missing))}")
    rows = []
    for r in reader:
        r = dict(r)
        r["options"] = [{"id": c, "text": r.pop(c, "")} for c in OPTION_CODES]
        rows.append(r)
    meta: dict[str, Any] = {}
    if rows:
        first = rows[0]
        meta = {"universidad": first.get("universidad"), "materia": first.get("materia"), "examen": first.get("examen")}
    return meta, rows


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_bank(data: bytes, file_name: str) -> ParsedBank:
    """Lee JSON o CSV y normaliza cada reactivo. Acumula errores por reactivo (no se detiene en el primero)."""
    if file_name.lower().endswith(".csv"):
        meta, rows = _rows_from_csv(data)
    elif file_name.lower().endswith(".json"):
        meta, rows = _rows_from_json(data)
    else:
        raise BankFormatError("Formato no soportado: usa .json o .csv.")

    bank = ParsedBank(metadata=meta, items=[])
    seen_ids: set[str] = set()
    status_counter: Counter[str] = Counter()
    no_page = 0
    for idx, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            bank.errors.append(f"Reactivo #{idx}: no es un objeto.")
            continue
        # Formato UDL v2 usa 'concept_id'; v1 usa 'conceptual_group'.
        if not raw.get("conceptual_group") and raw.get("concept_id"):
            raw = {**raw, "conceptual_group": raw["concept_id"]}
        rid = str(raw.get("id") or "").strip() or f"#{idx}"
        errs: list[str] = []

        def text_field(name: str, raw: dict[str, Any] = raw, errs: list[str] = errs, rid: str = rid) -> str:
            value = str(raw.get(name) or "").strip()
            if not value:
                errs.append(f"{rid}: falta '{name}'.")
            return value

        if rid in seen_ids:
            errs.append(f"{rid}: id duplicado en el archivo.")
        seen_ids.add(rid)

        module = _int(raw.get("module"))
        if module is None or module < 1:
            errs.append(f"{rid}: 'module' debe ser entero ≥ 1.")
        page_raw = raw.get("source_page")
        page = None if page_raw in (None, "") else _int(page_raw)
        if page_raw not in (None, "") and (page is None or page < 1):
            errs.append(f"{rid}: 'source_page' debe ser entero ≥ 1 o vacío.")
        if page is None and not errs:
            no_page += 1
        variant = _int(raw.get("variant") or 1) or 1

        bloom_raw = text_field("bloom")
        bloom = BLOOM_MAP.get(fold(bloom_raw))
        if bloom_raw and not bloom:
            errs.append(f"{rid}: nivel Bloom desconocido '{bloom_raw}'.")
        diff_raw = text_field("difficulty")
        difficulty = DIFFICULTY_MAP.get(fold(diff_raw))
        if diff_raw and not difficulty:
            errs.append(f"{rid}: dificultad desconocida '{diff_raw}'.")

        options: dict[str, str] = {}
        raw_opts = raw.get("options")
        if not isinstance(raw_opts, list) or len(raw_opts) != 4:
            errs.append(f"{rid}: debe tener exactamente 4 opciones.")
        else:
            for o in raw_opts:
                code = str((o or {}).get("id") or "").strip().upper()
                txt = str((o or {}).get("text") or "").strip()
                if code not in OPTION_CODES:
                    errs.append(f"{rid}: id de opción inválido '{code}'.")
                elif code in options:
                    errs.append(f"{rid}: opción {code} repetida.")
                elif not txt:
                    errs.append(f"{rid}: opción {code} vacía.")
                else:
                    options[code] = txt
            if len({fold(t) for t in options.values()}) != len(options):
                errs.append(f"{rid}: hay dos opciones con el mismo texto.")
        correct = str(raw.get("correct_option_id") or "").strip().upper()
        if correct not in OPTION_CODES:
            errs.append(f"{rid}: 'correct_option_id' debe ser A, B, C o D.")

        status = str(raw.get("status") or "draft").strip().lower()
        if status not in IMPORTABLE_STATUS:
            status_counter[status] += 1

        item = BankItem(
            external_id=rid,
            universidad=str(raw.get("universidad") or meta.get("universidad") or "").strip(),
            materia=str(raw.get("materia") or meta.get("materia") or "").strip(),
            examen=str(raw.get("examen") or meta.get("examen") or "").strip(),
            module_number=module or 0,
            topic=text_field("topic"),
            bloom=bloom or "",
            difficulty=difficulty or "",
            stem=text_field("stem"),
            options=options,
            correct_option=correct,
            rationale=text_field("rationale"),
            source_pdf=text_field("source_pdf"),
            source_page=page,
            conceptual_group=text_field("conceptual_group"),
            variant=variant,
            status_in_file=status,
            case_type=(str(raw.get("case_type")).strip() or None) if raw.get("case_type") else None,
        )
        if errs:
            bank.errors.extend(errs)
        else:
            bank.items.append(item)
    if not rows:
        bank.errors.append("El archivo no contiene reactivos.")
    for status, count in status_counter.items():
        bank.warnings.append(
            f"{count} reactivos con estado '{status}': se importan como 'draft' (requieren aprobación)."
        )
    if no_page:
        bank.warnings.append(
            f"{no_page} reactivos sin página citada (source_page vacío): sustento solo por PDF del módulo."
        )
    return bank


# ------------------------------------------------------- validación de contexto ---


@dataclass(frozen=True)
class CourseContext:
    university_code: str
    course_name: str
    module_numbers: frozenset[int]
    sources: dict[str, tuple[int, str, int | None]]  # file_name → (page_count, usage, module_number)


def validate_against_course(bank: ParsedBank, ctx: CourseContext) -> None:
    """Valida metadatos institucionales, módulos y citas contra la materia destino (agrega a ``bank.errors``)."""
    meta = bank.metadata
    if meta.get("universidad") and fold(str(meta["universidad"])) != fold(ctx.university_code):
        bank.errors.append(f"El banco es de la universidad '{meta['universidad']}', no de '{ctx.university_code}'.")
    if meta.get("materia") and fold(str(meta["materia"])) != fold(ctx.course_name):
        bank.errors.append(f"El banco es de la materia '{meta['materia']}', no de '{ctx.course_name}'.")
    for it in bank.items:
        if it.universidad and fold(it.universidad) != fold(ctx.university_code):
            bank.errors.append(f"{it.external_id}: universidad '{it.universidad}' no coincide.")
        if it.materia and fold(it.materia) != fold(ctx.course_name):
            bank.errors.append(f"{it.external_id}: materia '{it.materia}' no coincide.")
        if it.module_number not in ctx.module_numbers:
            bank.errors.append(f"{it.external_id}: el módulo {it.module_number} no existe en la materia.")
        src = ctx.sources.get(it.source_pdf)
        if src is None:
            bank.errors.append(f"{it.external_id}: fuente '{it.source_pdf}' no registrada en la materia.")
            continue
        page_count, usage, src_module = src
        if usage != "question_source":
            bank.errors.append(
                f"{it.external_id}: '{it.source_pdf}' es solo de inspiración; no puede citarse como sustento."
            )
        if it.source_page is not None and it.source_page > page_count:
            bank.errors.append(f"{it.external_id}: página {it.source_page} fuera de rango (máx. {page_count}).")
        if src_module is not None and src_module != it.module_number:
            bank.errors.append(
                f"{it.external_id}: la fuente corresponde al módulo {src_module}, no al {it.module_number}."
            )
