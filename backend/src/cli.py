"""CLI de administración.

    python -m src.cli ingest --tenant fundacion-epm --source excel \
        --file ./parrilla.xlsx --venue biblioteca-epm --month 2026-07

    python -m src.cli seed --tenant fundacion-epm

    python -m src.cli register-channel --tenant fundacion-epm
"""

import argparse
import asyncio
import sys
from pathlib import Path

from src.application.ingestion.import_excel import import_excel
from src.infrastructure.database.register_channel import register_channel
from src.infrastructure.database.seed import load_seed


def _parse_month(raw: str) -> tuple[int, int]:
    try:
        year, month = raw.split("-")
        parsed_year, parsed_month = int(year), int(month)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--month debe ser AAAA-MM, no {raw!r}") from exc
    if not 1 <= parsed_month <= 12:
        raise argparse.ArgumentTypeError(f"Mes fuera de rango: {parsed_month}")
    return parsed_year, parsed_month


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.cli", description="Administración de epm-wa-platform"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Importa programación desde una fuente")
    ingest.add_argument("--tenant", required=True)
    ingest.add_argument("--source", required=True, choices=["excel"])
    ingest.add_argument("--file", required=True, type=Path)
    ingest.add_argument(
        "--venue",
        required=True,
        help="Espacio al que pertenece la parrilla. No está en el archivo (§8).",
    )
    ingest.add_argument(
        "--month",
        required=True,
        help="AAAA-MM. Solo se usa si no se puede leer del título de la hoja.",
    )
    ingest.add_argument(
        "--force",
        action="store_true",
        help="Reprocesa aunque el contenido sea idéntico a una corrida anterior.",
    )

    seed = sub.add_parser("seed", help="Carga el seed de un tenant")
    seed.add_argument("--tenant", default="fundacion-epm")

    channel = sub.add_parser(
        "register-channel",
        help="Asocia un número de WhatsApp a un tenant (lo exige el webhook)",
    )
    channel.add_argument("--tenant", default="fundacion-epm")
    channel.add_argument(
        "--phone-number-id", help="Por omisión, META_PHONE_NUMBER_ID"
    )
    channel.add_argument("--waba-id", help="Por omisión, META_WABA_ID")
    channel.add_argument(
        "--display-number", default="", help="Número visible, solo informativo"
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.command == "seed":
        print((await load_seed(args.tenant)).render())  # noqa: T201
        return 0

    if args.command == "register-channel":
        registration = await register_channel(
            tenant_slug=args.tenant,
            phone_number_id=args.phone_number_id,
            waba_id=args.waba_id,
            display_number=args.display_number,
        )
        print(registration.render())  # noqa: T201
        return 0

    year, month = _parse_month(args.month)
    result = await import_excel(
        path=args.file,
        tenant_slug=args.tenant,
        venue_slug=args.venue,
        year=year,
        month=month,
        force=args.force,
    )
    print(result.render())  # noqa: T201
    # Código de salida distinto de cero si alguna fila quedó fuera: permite
    # que una tarea programada detecte que hubo problemas sin leer la salida.
    return 1 if result.report.rows_error else 0


def main() -> int:
    args = _build_parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
