"""Every module imports, and the agents, the pipeline and start_agents.py agree on order and ports."""

import importlib
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MODULES = [
    "agents.model_client",
    "agents.cv_text",
    "agents.job_analyst.__main__",
    "agents.cv_matcher.__main__",
    "agents.cover_letter_writer.__main__",
    "agents.application_reviewer.__main__",
    "orchestrator.pipeline",
    "orchestrator.agent_runner",
    "orchestrator.run_store",
    "orchestrator.__main__",
]
AGENT_MODULES = {
    "Job Analyst": "agents.job_analyst.__main__",
    "CV Matcher": "agents.cv_matcher.__main__",
    "Cover Letter Writer": "agents.cover_letter_writer.__main__",
    "Application Reviewer": "agents.application_reviewer.__main__",
}


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)


def test_pipeline_order_is_fixed():
    from orchestrator.pipeline import STEPS

    assert [s.name for s in STEPS] == list(AGENT_MODULES)


def test_agent_ports_match_pipeline_and_start_script():
    from orchestrator.pipeline import STEPS

    ports = {name: importlib.import_module(module).PORT for name, module in AGENT_MODULES.items()}
    assert [ports[s.name] for s in STEPS] == [9001, 9002, 9003, 9004]
    for step in STEPS:
        assert step.default_url == f"http://localhost:{ports[step.name]}"

    start_script = runpy.run_path(str(ROOT / "scripts" / "start_agents.py"), run_name="not_main")
    assert [url for _, _, url, _ in start_script["AGENTS"]] == [s.default_url for s in STEPS]


def test_agent_card_names_match_steps():
    for name, module in AGENT_MODULES.items():
        assert importlib.import_module(module).AGENT_CARD.name == name


def test_presets_set_every_agent_and_local_is_the_default():
    from agents.budget import has_price
    from agents.model_client import is_claude_model

    start_script = runpy.run_path(str(ROOT / "scripts" / "start_agents.py"), run_name="not_main")
    settings = [setting for *_, setting in start_script["AGENTS"]]
    presets = start_script["PRESETS"]
    for preset in presets.values():
        assert sorted(preset) == sorted(settings)
    assert not any(is_claude_model(m) for m in presets["local"].values())
    assert all(is_claude_model(m) and has_price(m) for m in presets["haiku"].values())
    assert 'default="local"' in (ROOT / "scripts" / "start_agents.py").read_text()


def test_each_agent_reads_the_setting_start_agents_sets():
    start_script = runpy.run_path(str(ROOT / "scripts" / "start_agents.py"), run_name="not_main")
    for _, module, _, setting in start_script["AGENTS"]:
        source = (ROOT / module.replace(".", "/") / "__main__.py").read_text()
        assert f'read_setting("{setting}")' in source
        assert "startup_check(" in source


def test_reviewer_step_sends_the_job_ad_as_a_labelled_text_part():
    from google.protobuf.json_format import MessageToDict

    from orchestrator.pipeline import APPLICATION_REVIEWER

    results = {
        "requirements": {"hard_skills_required": []}, "match_report": {"score_percent": 50},
        "cover_letter": "the letter", "job_ad": "the ad", "cv_pdf": b"%PDF", "cv_filename": "cv.pdf",
    }
    parts = APPLICATION_REVIEWER.build_parts(results)
    labels = {MessageToDict(p.metadata).get("content"): p.text for p in parts if p.HasField("text")}
    assert labels == {"cover_letter": "the letter", "job_ad": "the ad"}
