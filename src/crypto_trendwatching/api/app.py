"""FastAPI-приложение и минимальный веб-UI."""

from __future__ import annotations

import html as html_lib
import json
import logging
import statistics
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from importlib.metadata import version
from typing import Any, cast

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from plotly.offline import get_plotlyjs
from pydantic import BaseModel

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.application import dashboard as dashboard_lib
from crypto_trendwatching.application.bootstrap import build_pipeline
from crypto_trendwatching.application.config_loader import load_zones
from crypto_trendwatching.application.interpret import DISCLAIMER
from crypto_trendwatching.config import settings
from crypto_trendwatching.domain.models import ReportRun, TrendCandidate, Zone
from crypto_trendwatching.domain.ports import TrendRepository

logger = logging.getLogger(__name__)

APP_VERSION = version("crypto-trendwatching")

Lifespan = AsyncIterator[None]


class RunRequest(BaseModel):
    zone_id: str


class RunResponse(BaseModel):
    id: int
    status: str
    zone_id: str
    report_md: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> Lifespan:
    zones = {zone.id: zone for zone in load_zones(settings.config_dir / "topics.yaml")}
    repository: SqliteRepository = SqliteRepository(settings.database_path)
    app.state.zones = zones
    app.state.repository = repository
    logger.info("запуск сервиса", extra={"version": APP_VERSION})

    yield

    repository.close()
    logger.info("остановка сервиса")


def create_app() -> FastAPI:  # noqa: PLR0915
    application = FastAPI(
        title="Crypto Trendwatching",
        lifespan=lifespan,
        description="Персональный исследовательский дайджест по крипторынку",
        version=APP_VERSION,
    )

    @application.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        return HealthResponse(status="healthy", version=APP_VERSION)

    @application.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> str:
        repository: TrendRepository = request.app.state.repository
        zones: dict[str, Zone] = request.app.state.zones
        status_filter = request.query_params.get("status", "completed")
        all_runs = repository.list_runs()
        runs = all_runs
        if status_filter != "all":
            runs = [run for run in all_runs if run.status == status_filter]
        return _index_html(
            runs,
            list(zones.values()),
            status_filter,
            _median_duration_seconds(all_runs),
        )

    @application.delete("/runs/{run_id}")
    async def delete_run(request: Request, run_id: int) -> dict[str, bool]:
        repository: TrendRepository = request.app.state.repository
        deleted = repository.delete_run(run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="прогон не найден")
        return {"deleted": True}

    @application.post("/runs", response_model=RunResponse)
    async def start_run(
        request: Request, body: RunRequest, background_tasks: BackgroundTasks
    ) -> RunResponse:
        zones: dict[str, Zone] = request.app.state.zones
        zone = zones.get(body.zone_id)
        if zone is None:
            raise HTTPException(
                status_code=404, detail=f"зона не найдена: {body.zone_id}"
            )
        repository: TrendRepository = request.app.state.repository
        run_id = repository.save_run(
            ReportRun(status="running", zone_id=zone.id, started_at=_now_iso())
        )
        background_tasks.add_task(_run_in_background, zone, run_id)
        return RunResponse(id=run_id, status="running", zone_id=zone.id)

    @application.get("/runs")
    async def list_runs(request: Request) -> list[dict[str, Any]]:
        repository: TrendRepository = request.app.state.repository
        return [
            {
                "id": run.id,
                "status": run.status,
                "zone_id": run.zone_id,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
            for run in repository.list_runs()
        ]

    @application.get("/runs/{run_id}")
    async def get_run(request: Request, run_id: int) -> dict[str, Any]:
        repository: TrendRepository = request.app.state.repository
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="прогон не найден")
        return _run_to_dict(run)

    @application.get("/report/{run_id}")
    async def get_report(request: Request, run_id: int) -> dict[str, str]:
        repository: TrendRepository = request.app.state.repository
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="прогон не найден")
        return {"report_md": run.report_md or ""}

    @application.get("/runs/{run_id}/report", response_class=HTMLResponse)
    async def view_report(request: Request, run_id: int) -> HTMLResponse:
        repository: TrendRepository = request.app.state.repository
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="прогон не найден")
        if not run.report_md:
            return HTMLResponse(
                f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
                <title>Отчёт {run_id}</title></head><body>
                <h1>Отчёт {run_id}</h1><p>Отчёт ещё не готов (статус: {run.status}).</p>
                <p><a href="/">← к списку прогонов</a></p></body></html>"""
            )
        body = _markdown_to_html(run.report_md)
        download = (
            f'<a href="/report/{run_id}/docx">Скачать DOCX</a>'
            if run.report_docx
            else ""
        )
        return HTMLResponse(
            f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
            <title>Отчёт {run_id}</title></head><body>
            <p><a href="/">← к списку прогонов</a> | {download}</p>
            {body}
            <footer><em>{DISCLAIMER}</em></footer></body></html>"""
        )

    @application.get("/report/{run_id}/docx")
    async def get_report_docx(request: Request, run_id: int) -> Response:
        repository: TrendRepository = request.app.state.repository
        run = repository.get_run(run_id)
        if run is None or not run.report_docx:
            raise HTTPException(status_code=404, detail="DOCX не найден")
        return Response(
            content=run.report_docx,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="report_{run_id}.docx"'
            },
        )

    @application.get("/runs/{run_id}/candidates")
    async def get_candidates(request: Request, run_id: int) -> list[dict[str, Any]]:
        repository: TrendRepository = request.app.state.repository
        candidates = repository.list_trend_candidates(run_id)
        return [
            _candidate_to_dict(
                candidate,
                repository.list_evidence_bindings(candidate.id or 0),
                repository.list_evidence_verdicts(candidate.id or 0),
            )
            for candidate in candidates
        ]

    @application.get("/plotly.min.js", response_class=Response)
    async def plotly_js() -> Response:
        return Response(content=_plotly_js(), media_type="application/javascript")

    @application.get("/dashboard/{run_id}/funnel")
    async def dashboard_funnel(request: Request, run_id: int) -> dict[str, Any]:
        run = _get_run_or_404(request, run_id)
        return {"funnel": dashboard_lib.funnel_stages(run.funnel_json)}

    @application.get("/dashboard/{run_id}/maturity")
    async def dashboard_maturity(request: Request, run_id: int) -> dict[str, Any]:
        repository: TrendRepository = request.app.state.repository
        return {
            "maturity": dashboard_lib.maturity_counts(
                repository.list_trend_candidates(run_id)
            )
        }

    @application.get("/dashboard/{run_id}/onchain")
    async def dashboard_onchain(request: Request, run_id: int) -> dict[str, Any]:
        repository: TrendRepository = request.app.state.repository
        return {
            "observations": dashboard_lib.onchain_items(
                repository.list_onchain_observations_by_run(run_id)
            )
        }

    @application.get("/dashboard/{run_id}/whale")
    async def dashboard_whale(request: Request, run_id: int) -> dict[str, Any]:
        repository: TrendRepository = request.app.state.repository
        return {
            "whale": dashboard_lib.whale_items(repository.list_whale_transfers(run_id))
        }

    @application.get("/dashboard/{run_id}/catalysts")
    async def dashboard_catalysts(request: Request, run_id: int) -> dict[str, Any]:
        repository: TrendRepository = request.app.state.repository
        return {
            "catalysts": dashboard_lib.catalyst_items(repository.list_catalysts(run_id))
        }

    @application.get("/dashboard/{run_id}", response_class=HTMLResponse)
    async def dashboard_page(request: Request, run_id: int) -> HTMLResponse:
        repository: TrendRepository = request.app.state.repository
        run = _get_run_or_404(request, run_id)
        stages = dashboard_lib.funnel_stages(run.funnel_json)
        candidates = repository.list_trend_candidates(run_id)
        observations = repository.list_onchain_observations_by_run(run_id)
        transfers = repository.list_whale_transfers(run_id)
        catalysts = repository.list_catalysts(run_id)
        figures = {
            "funnel": dashboard_lib.funnel_figure(stages),
            "maturity": dashboard_lib.maturity_figure(
                dashboard_lib.maturity_counts(candidates)
            ),
            "onchain": dashboard_lib.onchain_figure(
                dashboard_lib.onchain_items(observations)
            ),
            "whale": dashboard_lib.whale_figure(dashboard_lib.whale_items(transfers)),
            "catalysts": dashboard_lib.catalyst_figure(
                dashboard_lib.catalyst_items(catalysts)
            ),
        }
        return HTMLResponse(_dashboard_html(run, figures))

    return application


def _get_run_or_404(request: Request, run_id: int) -> ReportRun:
    repository: TrendRepository = request.app.state.repository
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="прогон не найден")
    return run


@lru_cache(maxsize=1)
def _plotly_js() -> str:
    return cast(str, get_plotlyjs())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _run_in_background(zone: Zone, run_id: int) -> None:
    """Фоновый прогон: отдельный репозиторий/конвейер (изоляция соединения SQLite)."""
    repository = SqliteRepository(settings.database_path)
    try:
        pipeline = build_pipeline(repository)
        pipeline.execute(run_id, zone)
    except Exception:
        logger.exception("фоновый прогон %d упал с ошибкой", run_id)
    finally:
        repository.close()


def _run_to_dict(run: ReportRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "zone_id": run.zone_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "funnel_json": run.funnel_json,
        "report_md": run.report_md,
        "error": run.error,
    }


def _candidate_to_dict(
    candidate: TrendCandidate,
    bindings: list[Any],
    verdicts: list[Any],
) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "name": candidate.name,
        "definition": candidate.definition,
        "maturity": candidate.maturity,
        "catalog_numbers": candidate.catalog_numbers,
        "evidence": [
            {
                "source_url": binding.source_url,
                "quote": binding.quote,
                "catalog_number": binding.catalog_number,
            }
            for binding in bindings
        ],
        "verdicts": [
            {"verdict": verdict.verdict, "reason": verdict.reason}
            for verdict in verdicts
        ],
    }


def _index_html(
    runs: list[ReportRun],
    zones: list[Zone],
    status_filter: str,
    median_duration_seconds: float | None,
) -> str:
    zone_names = {zone.id: zone.name for zone in zones}
    rows = "".join(_run_row(run, zone_names, median_duration_seconds) for run in runs)
    zone_buttons = "".join(
        (
            f'<button onclick="startRun(&#39;{zone.id}&#39;, '
            f'&#39;{html_lib.escape(zone.name)}&#39;)">{html_lib.escape(zone.name)}</button> '
        )
        for zone in zones
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Crypto Trendwatching</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    .badge {{ padding: 2px 8px; border-radius: 10px; font-size: 0.85em; color: #fff; }}
    .completed {{ background: #2e7d32; }}
    .running {{ background: #1565c0; }}
    .failed {{ background: #c62828; }}
    .error {{ color: #c62828; font-size: 0.85em; max-width: 30em; }}
    .muted {{ color: #666; font-size: 0.85em; }}
    button {{ margin-right: 6px; cursor: pointer; }}
    .actions a {{ margin-right: 8px; }}
  </style>
</head>
<body>
  <h1>Crypto Trendwatching</h1>
  <p>Запустить прогон по зоне: {zone_buttons}</p>
  <h2>Прогоны</h2>
  <p>Фильтр: {_filter_bar(status_filter)}</p>
  <table>
    <thead>
      <tr><th>ID</th><th>Прогон</th><th>Статус</th><th>Начало</th><th>Конец</th><th>Ошибка</th><th>Действия</th></tr>
    </thead>
    <tbody>{rows or '<tr><td colspan="7">Нет прогонов с этим статусом.</td></tr>'}</tbody>
  </table>
  <footer><em>{DISCLAIMER}</em></footer>
  <script>
    async function startRun(zoneId, zoneName) {{
      if (!confirm('Запустить прогон по зоне «' + zoneName + '»?')) return;
      await fetch('/runs', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{zone_id: zoneId}})
      }});
      location.reload();
    }}
    async function deleteRun(runId) {{
      if (!confirm('Удалить прогон ' + runId + '?')) return;
      const response = await fetch('/runs/' + runId, {{method: 'DELETE'}});
      if (response.ok) {{ location.reload(); }} else {{ alert('Не удалось удалить'); }}
    }}
    let knownRunning = new Set();
    async function pollRuns() {{
      try {{
        const res = await fetch('/runs');
        const runs = await res.json();
        const running = new Set(runs.filter(r => r.status === 'running').map(r => r.id));
        for (const run of runs) {{
          if (knownRunning.has(run.id) && run.status !== 'running') {{
            const label = run.status === 'completed' ? 'завершён' : 'упал с ошибкой';
            notify('Прогон ' + run.id + ' ' + label, run.zone_id || '');
          }}
        }}
        knownRunning = running;
      }} catch (e) {{ /* игнорируем ошибки сети */ }}
    }}
    function notify(title, body) {{
      if ('Notification' in window && Notification.permission === 'granted') {{
        new Notification(title, {{ body }});
      }}
    }}
    if ('Notification' in window && Notification.permission === 'default') {{
      Notification.requestPermission();
    }}
    pollRuns();
    setInterval(pollRuns, 10000);
  </script>
</body>
</html>"""


def _filter_bar(current: str) -> str:
    options = [
        ("completed", "Завершённые"),
        ("running", "Выполняются"),
        ("failed", "С ошибкой"),
        ("all", "Все"),
    ]
    parts = []
    for value, label in options:
        if value == current:
            parts.append(f"<strong>{label}</strong>")
        else:
            parts.append(f'<a href="/?status={value}">{label}</a>')
    return " · ".join(parts)


def _format_datetime(value: str | None) -> str:
    """ISO-дата → человекочитаемый формат D/M/Y H:M:S (в локальном часовом поясе)."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return value


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _median_duration_seconds(runs: list[ReportRun]) -> float | None:
    """Медианная длительность завершённых прогонов (для оценки ETA)."""
    durations = []
    for run in runs:
        if run.status != "completed":
            continue
        started = _parse_iso(run.started_at)
        finished = _parse_iso(run.finished_at)
        if started is not None and finished is not None and finished > started:
            durations.append((finished - started).total_seconds())
    return statistics.median(durations) if durations else None


def _eta_display(run: ReportRun, median_seconds: float | None) -> str:
    """Оценка завершения для UI: «≈ дата» в будущем, иначе «задерживается (+N мин)»."""
    if run.status != "running" or median_seconds is None:
        return ""
    started = _parse_iso(run.started_at)
    if started is None:
        return ""
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    estimated = started + timedelta(seconds=median_seconds)
    now = datetime.now(UTC)
    if estimated <= now:
        minutes = int((now - estimated).total_seconds() // 60)
        return f"задерживается (+{minutes} мин)"
    return "≈ " + estimated.astimezone().strftime("%d/%m/%Y %H:%M:%S")


def _run_row(
    run: ReportRun,
    zone_names: dict[str, str],
    median_duration_seconds: float | None,
) -> str:
    actions = [f'<a href="/runs/{run.id}/report">Отчёт</a>']
    if run.status == "completed":
        actions.append(f'<a href="/dashboard/{run.id}">Дашборд</a>')
    if run.report_docx:
        actions.append(f'<a href="/report/{run.id}/docx">DOCX</a>')
    actions.append(
        f'<a href="#" onclick="deleteRun({run.id}); return false;" '
        f'style="color:#c62828">Удалить</a>'
    )
    error_cell = (
        f'<td class="error" title="{html_lib.escape(run.error or "")}">'
        f"{html_lib.escape((run.error or '')[:120])}</td>"
        if run.status == "failed"
        else "<td></td>"
    )
    end_cell = _format_datetime(run.finished_at)
    if run.status == "running":
        eta = _eta_display(run, median_duration_seconds)
        if eta:
            end_cell = f'<span class="muted">{html_lib.escape(eta)}</span>'
    title = zone_names.get(_run_zone_id(run) or "", f"Прогон {run.id}")
    description = _run_description(run)
    title_cell = f"<td><strong>{html_lib.escape(title)}</strong>"
    if description:
        title_cell += f'<br><span class="muted">{html_lib.escape(description)}</span>'
    title_cell += "</td>"
    return (
        "<tr>"
        f"<td>{run.id or ''}</td>"
        f"{title_cell}"
        f'<td><span class="badge {html_lib.escape(run.status)}">{html_lib.escape(run.status)}</span></td>'
        f"<td>{_format_datetime(run.started_at)}</td>"
        f"<td>{end_cell}</td>"
        f"{error_cell}"
        f'<td class="actions">{" · ".join(actions)}</td>'
        "</tr>"
    )


def _run_zone_id(run: ReportRun) -> str | None:
    """Идентификатор зоны прогона (из колонки, иначе из funnel_json — для старых прогонов)."""
    if run.zone_id:
        return run.zone_id
    if not run.funnel_json:
        return None
    try:
        data = json.loads(run.funnel_json)
    except json.JSONDecodeError:
        return None
    zone = data.get("zone") if isinstance(data, dict) else None
    return zone if isinstance(zone, str) else None


def _run_description(run: ReportRun) -> str:
    if not run.funnel_json:
        return ""
    try:
        data = json.loads(run.funnel_json)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    phases = data.get("phases") or {}
    parts = []
    signals = (phases.get("collect") or {}).get("signals")
    candidates = (phases.get("synthesize") or {}).get("candidates")
    verify = phases.get("verify") or {}
    passed = verify.get("passed")
    repeats = verify.get("rejected_repeats")
    if isinstance(signals, int):
        parts.append(f"{signals} сигналов")
    if isinstance(candidates, int):
        parts.append(f"{candidates} кандидатов")
    if isinstance(passed, int):
        parts.append(f"{passed} трендов")
    if isinstance(repeats, int) and repeats:
        parts.append(f"{repeats} повторов")
    return " · ".join(parts)


def _markdown_to_html(markdown: str) -> str:  # noqa: PLR0912
    """Минимальный рендер Markdown → HTML (заголовки, списки, code-блоки)."""
    lines: list[str] = []
    in_code = False
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.strip() == "```":
            if in_code:
                lines.append("</pre>")
                in_code = False
            else:
                if in_list:
                    lines.append("</ul>")
                    in_list = False
                lines.append("<pre>")
                in_code = True
            continue
        if in_code:
            lines.append(html_lib.escape(line))
            continue
        text = html_lib.escape(line)
        if line.startswith("### "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h3>{text[4:]}</h3>")
        elif line.startswith("## "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h2>{text[3:]}</h2>")
        elif line.startswith("# "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h1>{text[2:]}</h1>")
        elif line.startswith("- "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{text[2:]}</li>")
        elif line.strip():
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p>{text}</p>")
    if in_list:
        lines.append("</ul>")
    if in_code:
        lines.append("</pre>")
    return "\n".join(lines)


_CHART_BLOCKS = (
    ("funnel", "Воронка сигналов"),
    ("maturity", "Зрелость трендов"),
    ("onchain", "On-chain дельты (7д)"),
    ("whale", "Whale-потоки по активу"),
    ("catalysts", "Катализаторы (timeline)"),
)


def _dashboard_html(run: ReportRun, figures: dict[str, Any]) -> str:
    divs = "".join(
        f'<section><h3>{title}</h3><div id="{key}"></div></section>'
        for key, title in _CHART_BLOCKS
    )
    charts = []
    for key, _title in _CHART_BLOCKS:
        spec = figures[key].to_plotly_json()
        data = json.dumps(spec["data"], ensure_ascii=False)
        layout = json.dumps(spec.get("layout") or {}, ensure_ascii=False)
        charts.append(
            f"Plotly.newPlot('{key}', {data}, {layout}, {{responsive: true}});"
        )
    script = "\n    ".join(charts)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Дашборд {run.id}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
    section {{ margin-bottom: 2rem; }}
    h3 {{ margin-bottom: 0.4rem; }}
  </style>
  <script src="/plotly.min.js"></script>
</head>
<body>
  <p><a href="/">← к списку прогонов</a> | <a href="/runs/{run.id}/report">Отчёт</a></p>
  <h1>Дашборд прогона {run.id}</h1>
  <p class="muted">Зона: {html_lib.escape(run.zone_id or "—")} · {_format_datetime(run.started_at)} → {_format_datetime(run.finished_at)}</p>
  {divs}
  <footer><em>{DISCLAIMER}</em></footer>
  <script>
    {script}
  </script>
</body>
</html>"""


app = create_app()
