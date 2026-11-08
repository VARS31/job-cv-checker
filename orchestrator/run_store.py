"""RUN SAVED: everything a run produces goes into results/runs/<date-time>/.

run_log.json has one entry per step (agent, model, tokens, cost, seconds, questions and answers)
and, when the run ends, the totals.
"""

import json
from datetime import datetime

from agents.model_client import PROJECT_ROOT, RESULTS_DIR
from orchestrator.agent_runner import StepResult
from orchestrator.pipeline import Step


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RunStore:
    def __init__(self, context_id: str, inputs: dict) -> None:
        self.dir = RESULTS_DIR / "runs" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log = {
            "started": _now(),
            "finished": None,
            "status": "running",
            "message": None,
            "context_id": context_id,
            "inputs": inputs,
            "steps": [],
        }
        self._write_log()

    @property
    def relative_dir(self) -> str:
        return str(self.dir.relative_to(PROJECT_ROOT))

    def add_step(self, result: StepResult) -> None:
        self.log["steps"].append(result.for_log())
        self._write_log()  # written after every step, so a stopped run still has its log

    def save_outputs(self, step: Step, results: dict) -> None:
        for key, filename in step.outputs.items():
            value = results[key]
            text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
            (self.dir / filename).write_text(text, encoding="utf-8")

    def finish(self, status: str, message: str | None = None) -> None:
        steps = self.log["steps"]
        totals = {
            "cost_usd": round(sum(s["cost_usd"] for s in steps), 6),
            "input_tokens": sum(s["input_tokens"] for s in steps),
            "output_tokens": sum(s["output_tokens"] for s in steps),
            "seconds": round(sum(s["seconds"] for s in steps), 1),
        }
        self.log.update(finished=_now(), status=status, message=message, totals=totals)
        self._write_log()

    def _write_log(self) -> None:
        (self.dir / "run_log.json").write_text(json.dumps(self.log, indent=2, ensure_ascii=False), encoding="utf-8")
