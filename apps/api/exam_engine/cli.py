"""Herramientas de operación.

    python -m exam_engine.cli seed-catalog seeds/udl_siaf_catalog.json
    python -m exam_engine.cli create-admin --username admin --role platform_admin --temporary
    python -m exam_engine.cli bank-report banco.json --quota 50 --max-variants 2 --seconds 20 --out reporte.md

La contraseña de create-admin se lee de ADMIN_PASSWORD o se pide por teclado (nunca como argumento,
para que no quede en el historial de la terminal).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path


def _create_admin(a: argparse.Namespace) -> None:
    from .services.admin_auth import create_admin

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Contraseña: ")
    if not password:
        raise SystemExit("Contraseña vacía.")
    print(
        create_admin(
            username=a.username,
            password=password,
            display_name=a.display_name,
            role=a.role,
            university_code=a.university,
            temporary=a.temporary,
        )
    )


def _seed(a: argparse.Namespace) -> None:
    from .seeding import seed_catalog

    print(seed_catalog(Path(a.file)))


def _bank_report(a: argparse.Namespace) -> None:
    from .services.bank_format import parse_bank
    from .services.quality import build_report, render_markdown

    data = Path(a.file).read_bytes()
    bank = parse_bank(data, a.file)
    if bank.errors:
        print(f"{len(bank.errors)} errores de formato; primeros:", *bank.errors[:20], sep="\n  ", file=sys.stderr)
    rep = build_report(
        bank.items, per_module_quota=a.quota, max_variants_per_group=a.max_variants, seconds_per_question=a.seconds
    )
    note = (
        f"Archivo: `{Path(a.file).name}` · Configuración evaluada: {a.quota} por módulo, máx. {a.max_variants} "
        f"variante(s) por grupo conceptual, {a.seconds} s por pregunta.\n\nAdvertencias de importación: "
        + ("; ".join(bank.warnings) or "ninguna")
    )
    md = render_markdown(
        rep, bank.metadata.get("materia", "banco") + " — " + str(bank.metadata.get("examen", "")), note
    )
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"Reporte escrito en {a.out}")
    else:
        print(md)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="exam_engine.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create-admin", help="Crea o restablece un docente/administrador")
    c.add_argument("--username", required=True)
    c.add_argument("--display-name", default="Administrador")
    c.add_argument("--role", choices=["platform_admin", "university_admin", "teacher"], default="platform_admin")
    c.add_argument("--university", help="Código de universidad (no aplica a platform_admin)")
    c.add_argument("--temporary", action="store_true", help="Obliga a cambiar la contraseña al entrar")
    c.set_defaults(fn=_create_admin)

    sd = sub.add_parser("seed-catalog", help="Siembra universidad, materia, módulos y fuentes desde JSON")
    sd.add_argument("file")
    sd.set_defaults(fn=_seed)

    r = sub.add_parser("bank-report", help="Reporte de calidad de un banco (sin BD)")
    r.add_argument("file")
    r.add_argument("--quota", type=int, default=50)
    r.add_argument("--max-variants", type=int, default=2)
    r.add_argument("--seconds", type=int, default=20)
    r.add_argument("--out")
    r.set_defaults(fn=_bank_report)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
