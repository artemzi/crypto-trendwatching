"""CLI entry points: serve (web UI), run (pipeline), eval (метрики)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.application.bootstrap import build_onchain, build_pipeline
from crypto_trendwatching.application.config_loader import load_zones
from crypto_trendwatching.application.eval import (
    EvalMetrics,
    compute_metrics,
    load_golden_set,
    render_metrics_report,
)
from crypto_trendwatching.application.retrospective import (
    render_retro_report,
    run_retrospective,
)
from crypto_trendwatching.config import settings
from crypto_trendwatching.domain.models import Zone

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="crypto-trendwatching")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="запустить веб-UI (FastAPI)")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    run = subparsers.add_parser("run", help="прогнать конвейер по зоне(ам)")
    zone_group = run.add_mutually_exclusive_group(required=True)
    zone_group.add_argument("--zone", help="id зоны из config/topics.yaml")
    zone_group.add_argument(
        "--all", action="store_true", help="прогнать все включённые зоны"
    )

    eval_parser = subparsers.add_parser(
        "eval", help="посчитать precision/recall по золотому сету"
    )
    eval_parser.add_argument("--golden", default="data/eval")
    eval_parser.add_argument("--zone", default=None)

    subparsers.add_parser(
        "retro", help="ретроспективная проверка pump-флагов (памп vs тренд)"
    )

    args = parser.parse_args(argv)

    if args.command == "serve":
        uvicorn.run(
            "crypto_trendwatching.api.app:app",
            host=args.host or settings.app_host,
            port=args.port or settings.app_port,
            log_level=settings.log_level.lower(),
        )
    elif args.command == "run":
        if args.all:
            _run_all()
        else:
            _run(args.zone)
    elif args.command == "eval":
        _run_eval(args.golden, args.zone)
    elif args.command == "retro":
        _run_retro()


def _run(zone_id: str) -> None:
    logging.basicConfig(level=logging.INFO)
    zones = {zone.id: zone for zone in load_zones(settings.config_dir / "topics.yaml")}
    zone = zones.get(zone_id)
    if zone is None:
        print(f"зона не найдена: {zone_id}", file=sys.stderr)
        raise SystemExit(1)
    _run_zones([zone])


def _run_all() -> None:
    logging.basicConfig(level=logging.INFO)
    zones = [z for z in load_zones(settings.config_dir / "topics.yaml") if z.enabled]
    _run_zones(zones)


def _run_zones(zones: list[Zone]) -> None:
    repository = SqliteRepository(settings.database_path)
    pipeline = build_pipeline(repository)
    try:
        for zone in zones:
            try:
                run = pipeline.run(zone)
                print(
                    f"прогон {run.id} завершён для зоны {zone.id} (статус: {run.status})"
                )
            except Exception:
                logger.exception("зона %s упала с ошибкой", zone.id)
    finally:
        repository.close()


def _run_eval(golden_path: str, zone_id: str | None) -> None:
    logging.basicConfig(level=logging.INFO)
    path = Path(golden_path)
    golden_files = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
    golden = [zone for file in golden_files for zone in load_golden_set(file)]
    zones = {zone.id: zone for zone in load_zones(settings.config_dir / "topics.yaml")}

    repository = SqliteRepository(settings.database_path)
    pipeline = build_pipeline(repository)
    per_zone: dict[str, EvalMetrics] = {}
    try:
        for golden_zone in golden:
            if zone_id and golden_zone.zone_id != zone_id:
                continue
            zone = zones.get(golden_zone.zone_id)
            if zone is None:
                continue
            run = pipeline.run(zone)
            predicted = {
                candidate.name
                for candidate in repository.list_trend_candidates(run.id or 0)
            }
            per_zone[golden_zone.zone_id] = compute_metrics(
                predicted, golden_zone.expected()
            )
    finally:
        repository.close()
    print(render_metrics_report(per_zone))


def _run_retro() -> None:
    logging.basicConfig(level=logging.INFO)
    repository = SqliteRepository(settings.database_path)
    try:
        verdicts = run_retrospective(repository, build_onchain())
    finally:
        repository.close()
    print(render_retro_report(verdicts))
