import asyncio
import json
import os
import tempfile
import threading

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from simulation_ui.runner import get_scenarios, SimulationRunner
from simulation_ui.analyzer import analyze as ai_analyze
from gagarin.checkpoint import (
    read_altitudes, convert_start_point,
    compute_true_trajectory, run_tercom, collect_result,
)
from simulation_ui.svg_generator import svg_checkpoint_profile

app = FastAPI(title="Gagarin Simulation UI")

static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    index_path = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>index.html не найден</h1>")


@app.get("/api/scenarios")
async def api_scenarios():
    return get_scenarios()


@app.post("/api/analyze/{scenario_id}")
async def api_analyze(scenario_id: str, request: Request):
    body = await request.json()
    steps = body.get("steps", [])
    if not steps:
        raise HTTPException(status_code=400, detail="Нет данных шагов для анализа")
    result = await ai_analyze(steps)
    return result


@app.get("/api/simulate/{scenario_id}")
async def api_simulate(scenario_id: str):
    scenarios = get_scenarios()
    if scenario_id not in scenarios:
        raise HTTPException(status_code=404, detail=f"Сценарий '{scenario_id}' не найден")
    if not scenarios[scenario_id].get("exists", False):
        raise HTTPException(status_code=404, detail=f"DEM-файл для '{scenario_id}' не найден")

    async def event_generator():
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        stop_event = threading.Event()

        def run_pipeline():
            runner = SimulationRunner(scenario_id)
            for step in runner.run():
                if stop_event.is_set():
                    return
                loop.call_soon_threadsafe(queue.put_nowait, step)
            loop.call_soon_threadsafe(queue.put_nowait, None)

        fut = loop.run_in_executor(None, run_pipeline)

        try:
            while True:
                step = await queue.get()
                if step is None:
                    break
                yield {"event": "step", "data": json.dumps(step, ensure_ascii=False, default=str)}
        except asyncio.CancelledError:
            stop_event.set()
            fut.cancel()
            raise
        finally:
            if not fut.done():
                stop_event.set()
                fut.cancel()
            try:
                await fut
            except asyncio.CancelledError:
                pass
        yield {"event": "complete", "data": "{}"}

    return EventSourceResponse(event_generator())


@app.get("/checkpoint")
async def checkpoint_page():
    path = os.path.join(templates_dir, "checkpoint.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>checkpoint.html не найден</h1>")


@app.post("/api/checkpoint/run")
async def api_checkpoint_run(
    dem_file: UploadFile = File(...),
    altitudes_file: UploadFile = File(...),
    start_x: float = Form(...),
    start_y: float = Form(...),
    coord_type: str = Form("pixel"),
    azimuth: float = Form(...),
    speed: float = Form(60.0),
    freq: float = Form(10.0),
):
    from gagarin.dem_loader import DEMLoader

    with tempfile.TemporaryDirectory() as tmpdir:
        dem_path = os.path.join(tmpdir, dem_file.filename or "dem.tif")
        with open(dem_path, "wb") as f:
            f.write(await dem_file.read())

        alt_path = os.path.join(tmpdir, "altitudes.txt")
        with open(alt_path, "wb") as f:
            f.write(await altitudes_file.read())

        dem = DEMLoader(dem_path)
        altitudes = read_altitudes(alt_path)

        start_lat, start_lon = convert_start_point(dem, start_x, start_y, coord_type)
        n_steps = len(altitudes)
        true_lats, true_lons = compute_true_trajectory(
            start_lat, start_lon, azimuth, speed, n_steps, freq,
        )

        estimates, estimate_indices = run_tercom(dem, altitudes, start_lat, start_lon,
                               estimated_speed=speed, estimated_azimuth=azimuth,
                               freq_hz=freq)

        result = collect_result(dem, true_lats, true_lons, estimates, altitudes, estimate_indices=estimate_indices)
        data = result.to_dict()
        data["start_lat"] = start_lat
        data["start_lon"] = start_lon
        data["profile_svg"] = svg_checkpoint_profile(
            data.get("radar_altitudes", []),
            data.get("true_terrain", []),
        )

        return data
