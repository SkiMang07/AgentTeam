from __future__ import annotations

import json
import re
from pathlib import Path

from app.state import SharedState
from tools.openai_client import ResponsesClient

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "qa.md"


class QAAgent:
    def __init__(self, client: ResponsesClient) -> None:
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def run(self, state: SharedState) -> SharedState:
        work_order = state.get("work_order", {})
        pod_task_brief = state.get("pod_task_brief", "")
        pod_artifacts = state.get("pod_artifacts") or {}
        backend_output = pod_artifacts.get("backend", "(no backend output)")
        frontend_output = pod_artifacts.get("frontend", "(no frontend output)")

        raw = self._client.ask(
            system_prompt=self._prompt,
            user_prompt=(
                "Review the following backend and frontend code drafts and return strict JSON "
                "with keys: findings (array of strings), verdict (\"pass\" or \"revise\").\n\n"
                f"Task:\n{state['user_task']}\n\n"
                f"Work order objective:\n{work_order.get('objective', '')}\n\n"
                f"Pod task brief:\n{pod_task_brief or '(none provided)'}\n\n"
                f"Backend output:\n{backend_output}\n\n"
                f"Frontend output:\n{frontend_output}"
            ),
        )

        data = self._safe_parse(raw)
        findings = self._extract_findings(data)
        verdict = self._extract_verdict(data)

        return {
            **state,
            "pod_qa_findings": findings,
            "pod_qa_verdict": verdict,
            "status": "qa_reviewed",
            "model_metadata": {
                **state.get("model_metadata", {}),
                "qa_raw": raw,
            },
        }

    @staticmethod
    def _safe_parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return {}

    @staticmethod
    def _extract_findings(data: dict) -> list[str]:
        findings = data.get("findings")
        if isinstance(findings, list) and all(isinstance(f, str) for f in findings):
            return findings
        return ["QA parse note: findings field missing or malformed in model output."]

    @staticmethod
    def _extract_verdict(data: dict) -> str:
        verdict = data.get("verdict")
        if verdict in ("pass", "revise"):
            return verdict
        return "revise"
