import asyncio
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from simulation_ui.runner import get_scenarios, SimulationRunner  # noqa: E402

app = FastAPI(title="Gagarin Simulation UI")

static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    index_path = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_path):
        return HTMLResponse(open(index_path, encoding="utf-8").read())
    return HTMLResponse("<h1>index.html not found</h1>")


@app.get("/api/scenarios")
async def api_scenarios():
    return get_scenarios()


@app.get("/api/simulate/{scenario_id}")
async def api_simulate(scenario_id: str):
    if scenario_id not in get_scenarios():
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    if not get_scenarios()[scenario_id].get("exists", False):
        raise HTTPException(status_code=404, detail=f"DEM file for '{scenario_id}' not found")

    async def event_generator():
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def run_pipeline():
            runner = SimulationRunner(scenario_id)
            for step in runner.run():
                queue.put_nowait(step)
            queue.put_nowait(None)

        task = loop.run_in_executor(None, run_pipeline)

        while True:
            step = await queue.get()
            if step is None:
                break
            yield {"event": "step", "data": json.dumps(step, ensure_ascii=False, default=str)}

        await task
        yield {"event": "complete", "data": "{}"}

    return EventSourceResponse(event_generator())
