import httpx
import asyncio
import os


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
TIMEOUT_S = int(os.environ.get("OLLAMA_TIMEOUT", "600"))


def _format_metrics(steps: list[dict]) -> str:
    lines = []
    for s in steps:
        m = s.get("metrics", {}) or {}
        kv = " | ".join(f"{k}={v}" for k, v in m.items() if v is not None)
        lines.append(f"  [{s.get('phase','?')}] {s.get('title','?')} — {kv}")
    return "\n".join(lines)


def build_log(steps: list[dict]) -> str:
    scenario_info = "—"
    for s in steps:
        if s.get("id") == "step-result":
            m = s.get("metrics", {})
            scenario_info = f"оценок={m.get('n_estimates', '?')} средний_NCC={m.get('avg_correlation', '?')}"
            break
    lines = [
        "ЛОГ СИМУЛЯЦИИ TERCOM",
        "=====================",
        f"Сценарий: {scenario_info}",
        f"Всего шагов: {len(steps)}",
        "",
        "ПОШАГОВЫЕ МЕТРИКИ:",
        _format_metrics(steps),
    ]
    for s in steps:
        m = s.get("metrics", {}) or {}
        filtered = {k: v for k, v in m.items() if k != "trajectory"}
        lines.append(f"--- Шаг {s.get('number','?')} {s.get('title','?')} ---")
        lines.append(str(filtered))
        lines.append(s.get("explanation", "")[:200])
    log = "\n".join(lines)
    return log[:8000] if len(log) > 8000 else log


def _build_prompt(log: str) -> str:
    return (
        "Ты — эксперт по TERCOM-навигации для БПЛА. "
        "Проанализируй лог симуляции и найди аномалии, проблемы в работе алгоритма. "
        "Предложи улучшения (новые этапы обработки, фильтры, параметры).\n\n"
        f"{log}\n\n"
        "Ответь строго в формате:\n"
        "SUMMARY: краткое саммари (2-3 предложения)\n\n"
        "ANOMALIES:\n"
        "- [high|medium|low] описание аномалии\n"
        "- [high|medium|low] описание аномалии\n\n"
        "SUGGESTIONS:\n"
        "- описание предложения\n"
        "- описание предложения"
    )


def _parse_response(text: str) -> dict:
    anomalies = []
    suggestions = []
    summary = ""
    section = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):].strip()
            section = "summary"
        elif line.startswith("ANOMALIES:"):
            section = "anomalies"
        elif line.startswith("SUGGESTIONS:"):
            section = "suggestions"
        elif section == "summary" and summary == "":
            summary = line
        elif section == "anomalies" and line.startswith("-"):
            rest = line[1:].strip()
            severity = "low"
            if rest.lower().startswith("[high]"):
                severity = "high"
                rest = rest[6:].strip()
            elif rest.lower().startswith("[medium]"):
                severity = "medium"
                rest = rest[8:].strip()
            elif rest.lower().startswith("[low]"):
                severity = "low"
                rest = rest[5:].strip()
            anomalies.append({"severity": severity, "text": rest})
        elif section == "suggestions" and line.startswith("-"):
            suggestions.append({"text": line[1:].strip()})

    if not anomalies and not suggestions and not summary:
        summary = text[:300] if len(text) > 300 else text

    return {
        "summary": summary or "Модель не вернула структурированный ответ.",
        "anomalies": anomalies,
        "suggestions": suggestions,
        "raw_response": text,
    }


async def analyze(steps: list[dict]) -> dict:
    log = build_log(steps)
    prompt = _build_prompt(log)
    try:
        async def _request():
            async with httpx.AsyncClient(timeout=None) as client:
                resp = await client.post(
                    OLLAMA_URL,
                    json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")
        raw = await asyncio.wait_for(_request(), timeout=TIMEOUT_S)
    except httpx.ConnectError:
        return {"error": "Ollama не отвечает на localhost:11434. Запусти `ollama serve`."}
    except httpx.HTTPStatusError as e:
        return {"error": f"Ollama вернул ошибку: {e.response.status_code}"}
    except asyncio.TimeoutError:
        return {"error": f"Модель {OLLAMA_MODEL} не ответила за {TIMEOUT_S}с. Попробуйте увеличить OLLAMA_TIMEOUT (сейчас {TIMEOUT_S}с) или проверить загрузку модели."}
    result = _parse_response(raw)
    result["model"] = OLLAMA_MODEL
    return result
