import asyncio
import json
import os
import sys
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from simulation_ui.runner import get_scenarios, SimulationRunner  # noqa: E402
from simulation_ui.analyzer import analyze as ai_analyze  # noqa: E402

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
