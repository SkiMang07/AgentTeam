"""FastAPI server that exposes the Agent Team graph over HTTP with SSE streaming.

Run from the agent_team directory:
    uvicorn app.server:app --reload

Then open http://localhost:8000 in your browser.
"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from agents.advisor import AdvisorAgent
from agents.advisor_router import AdvisorRouterAgent
from agents.backend import BackendAgent
from agents.chief_of_staff import ChiefOfStaffAgent
from agents.communication_influence_advisor import CommunicationInfluenceAdvisorAgent
from agents.entrepreneur_execution_advisor import EntrepreneurExecutionAdvisorAgent
from agents.frontend import FrontendAgent
from agents.growth_mindset_advisor import GrowthMindsetAdvisorAgent
from agents.jt import JTAgent
from agents.leadership_culture_advisor import LeadershipCultureAdvisorAgent
from agents.qa import QAAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.strategy_systems_advisor import StrategySystemsAdvisorAgent
from agents.writer import WriterAgent
from app.config import get_settings
from app.graph import build_graph
from app.jt_request import detect_jt_request
from app.state import SharedState, empty_project_memory, normalize_project_memory
from tools.agent_knowledge_loader import AgentKnowledgeLoader
from tools.file_writer import FileWriter
from tools.local_file_reader import load_local_files
from tools.obsidian_context import ObsidianContextTool
from tools.openai_client import ResponsesClient
from tools.vault_session_loader import VaultSessionLoader
from tools.voice_loader import VoiceLoader

app = FastAPI(title="Agent Team UI Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global agent cache ────────────────────────────────────────────────────────
# Agents are expensive to initialise (prompt loading, client setup). Cache them
# once and rebuild the LangGraph per-request (graph compilation is cheap).
_agents: dict[str, Any] | None = None
_agents_lock = threading.Lock()
_default_output_dir: str = ""  # Populated from OUTPUT_DIR in .env at first agent init
_vault_session_loader: VaultSessionLoader | None = None  # Set in _init_agents()

# ── In-flight session state ───────────────────────────────────────────────────
# session_id -> {event_queue, review_event, review_result}
_sessions: dict[str, dict[str, Any]] = {}

# ── Session-level project memory (persists across runs in one browser tab) ────
_session_memory: dict[str, Any] = {}


# ── Agent initialisation ──────────────────────────────────────────────────────

def _init_agents() -> dict[str, Any]:
    """Create and return all agent instances. Called once at startup."""
    global _default_output_dir, _vault_session_loader
    try:
        settings = get_settings()
    except ValueError as e:
        raise RuntimeError(f"Configuration error: {e}") from e

    if settings.output_dir:
        _default_output_dir = settings.output_dir
        print(f"[server] Default output directory: {_default_output_dir}")

    client = ResponsesClient(settings)

    obsidian_tool: ObsidianContextTool | None = None
    agent_knowledge_loader: AgentKnowledgeLoader | None = None
    if settings.obsidian_vault_path:
        obsidian_tool = ObsidianContextTool(settings.obsidian_vault_path, client)
        if not obsidian_tool.available:
            print(f"[server] Warning: OBSIDIAN_VAULT_PATH set but not found: {settings.obsidian_vault_path}")
            obsidian_tool = None
        else:
            print(f"[server] Obsidian vault loaded: {settings.obsidian_vault_path}")

        _project_root = Path(__file__).resolve().parents[2]  # AgentTeam/
        agent_knowledge_loader = AgentKnowledgeLoader(str(_project_root))
        if agent_knowledge_loader.available:
            print(f"[server] Agent knowledge layer loaded: {str(_project_root)}/agent_team/agent_docs")
        else:
            print("[server] Warning: Agent knowledge layer not found (agent_team/agent_docs missing)")
            agent_knowledge_loader = None

        # Vault session loader — broad, always-on scan of all CLAUDE.md files.
        # Used to orient the CoS at intake time without requiring the user to
        # specify any local files explicitly.
        _vault_loader = VaultSessionLoader(settings.obsidian_vault_path)
        if _vault_loader.available:
            _vault_session_loader = _vault_loader
            print(
                f"[server] Vault session loader ready: {_vault_loader.vault_name}"
                f" ({_vault_loader.vault_path})"
            )
        else:
            _vault_session_loader = None
            print("[server] Warning: VaultSessionLoader: path not found or not a directory")

    voice_loader = VoiceLoader(settings.voice_file_path)
    if voice_loader.available:
        print(f"[server] Voice/style guide loaded: {settings.voice_file_path}")

    return {
        "chief_of_staff": ChiefOfStaffAgent(
            client,
            obsidian_tool=obsidian_tool,
            agent_knowledge_loader=agent_knowledge_loader,
            voice_loader=voice_loader,
        ),
        "jt": JTAgent(client),
        "researcher": ResearcherAgent(client, obsidian_tool=obsidian_tool),
        "reviewer": ReviewerAgent(client),
        "writer": WriterAgent(client, voice_loader=voice_loader),
        "backend": BackendAgent(client),
        "frontend": FrontendAgent(client),
        "qa": QAAgent(client),
        "advisor": AdvisorAgent(client),
        "advisor_router": AdvisorRouterAgent(client),
        "strategy_systems_advisor": StrategySystemsAdvisorAgent(client),
        "leadership_culture_advisor": LeadershipCultureAdvisorAgent(client),
        "communication_influence_advisor": CommunicationInfluenceAdvisorAgent(client),
        "growth_mindset_advisor": GrowthMindsetAdvisorAgent(client),
        "entrepreneur_execution_advisor": EntrepreneurExecutionAdvisorAgent(client),
    }


def get_agents() -> dict[str, Any]:
    global _agents
    if _agents is None:
        with _agents_lock:
            if _agents is None:
                _agents = _init_agents()
    return _agents


def make_graph(on_node_enter=None, on_node_exit=None, human_review_fn=None, file_writer=None):
    """Build a fresh LangGraph instance with the given per-run callbacks."""
    a = get_agents()
    return build_graph(
        a["chief_of_staff"],
        a["jt"],
        a["researcher"],
        a["reviewer"],
        a["writer"],
        a["backend"],
        a["frontend"],
        a["qa"],
        advisor=a["advisor"],
        advisor_router=a["advisor_router"],
        strategy_systems_advisor=a["strategy_systems_advisor"],
        leadership_culture_advisor=a["leadership_culture_advisor"],
        communication_influence_advisor=a["communication_influence_advisor"],
        growth_mindset_advisor=a["growth_mindset_advisor"],
        entrepreneur_execution_advisor=a["entrepreneur_execution_advisor"],
        on_node_enter=on_node_enter,
        on_node_exit=on_node_exit,
        human_review_fn=human_review_fn,
        file_writer=file_writer,
    )


# ── Request / response models ─────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    session_id: str
    approved: bool
    notes: str = ""


class IntakeRequest(BaseModel):
    task: str
    branch: str = "plan"
    files_path: str = ""
    pinned_folders: str = ""  # comma-separated folder names to force into full tier


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    """Serve the live-wired console UI."""
    ui_path = (
        Path(__file__).parent.parent.parent
        / "design"
        / "ui_prototype_v1"
        / "index.html"
    )
    if ui_path.exists():
        return HTMLResponse(ui_path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail=f"UI not found at {ui_path}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def get_config():
    """
    Return server configuration for the UI.

    Called on page load so the UI can display which vault is active without
    the user having to configure anything manually.
    """
    get_agents()  # ensure _vault_session_loader is populated (idempotent after first call)
    loader = _vault_session_loader
    if loader is None or not loader.available:
        return {"vault_path": "", "vault_name": "", "vault_status": "not_configured"}
    return {
        "vault_path": loader.vault_path,
        "vault_name": loader.vault_name,
        "vault_status": "loaded",
    }


@app.post("/intake")
def intake(req: IntakeRequest):
    """
    Run a CoS pre-dispatch intake analysis and return the result synchronously.

    The UI calls this before the main /run to give the CoS a chance to:
    - Confirm it has enough context to dispatch confidently, or
    - Return 2-3 targeted questions for the user to answer first.

    Response shape:
      {
        ready: bool,
        questions: list[str],       # empty when ready=true
        analysis: str,              # CoS's read of the task
        suggested_branch: str,      # "plan" | "build" | "brainstorm"
        suggested_approach: str
      }
    """
    try:
        agents = get_agents()
        cos = agents["chief_of_staff"]

        # Per-run file overrides (still accepted but no longer required — vault
        # context is now injected automatically from the server-side vault loader).
        files_list = [f.strip() for f in req.files_path.split(",") if f.strip()]
        file_read_result = load_local_files(files_list) if files_list else {"file_contents": {}}

        # Auto-inject vault context. Pinned folders (user-specified) always get
        # full content; remaining folders are split into recent-full and compact-index.
        pinned_list = [f.strip() for f in req.pinned_folders.split(",") if f.strip()]
        vault_ctx = ""
        if _vault_session_loader and _vault_session_loader.available:
            vault_ctx = _vault_session_loader.render_for_prompt(
                pinned_folders=pinned_list
            )

        result = cos.intake(
            req.task,
            branch_hint=req.branch,
            file_context=file_read_result.get("file_contents", {}),
            vault_context=vault_ctx,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        # Intake failure is non-fatal — the UI should fall back to /run directly
        return {
            "ready": True,
            "questions": [],
            "analysis": f"Intake unavailable ({exc}). Proceeding directly.",
            "suggested_branch": req.branch,
            "suggested_approach": "Dispatching with available context.",
        }


@app.post("/approve")
def approve(req: ApproveRequest):
    """Called by the browser approval UI to unblock the human_review gate."""
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or already closed")
    session["review_result"] = {"approved": req.approved, "notes": req.notes}
    session["review_event"].set()
    return {"ok": True}


@app.get("/open-folder")
def open_folder(path: str):
    """Open a folder or file in the OS file manager (macOS Finder / Linux Nautilus).

    Called by the UI after a run produces files, letting the user reveal them
    without leaving the browser.
    """
    import subprocess
    import platform

    target = Path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    system = platform.system()
    try:
        if system == "Darwin":
            # -R reveals the item in Finder (selects it in its parent folder)
            subprocess.Popen(["open", "-R", str(target)])
        elif system == "Linux":
            subprocess.Popen(["xdg-open", str(target.parent)])
        else:
            subprocess.Popen(["explorer", str(target.parent)])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not open folder: {exc}") from exc

    return {"ok": True, "path": str(target)}


@app.get("/run")
def run_stream(
    task: str,
    branch: str = "plan",
    jt_enabled: bool = False,
    files_path: str = "",
    web_search: bool = False,
    output_format: str = "Chat",
    mem_session: str = "",
    output_dir: str = "",
    allowed_read_dirs: str = "",
    pinned_folders: str = "",
):
    """
    SSE stream that runs the agent graph and emits progress events.

    Events emitted (JSON in `data:` field):
        {type: "session",       session_id: str}
        {type: "node_start",    node: str}
        {type: "node_complete", node: str, elapsed_ms: int}
        {type: "human_review",  draft: str, reviewer_findings: dict}
        {type: "final",         output: str, status: str, execution_path: list,
                                files_created: list[str]}
        {type: "error",         message: str}
        {type: "heartbeat"}

    File output params:
        output_dir: Absolute path to a directory where the agents may write
            output files for this run. A per-run subdirectory
            ``run_<session_id[:8]>`` is created inside it automatically.
            If omitted, no files are written.
        allowed_read_dirs: Comma-separated list of absolute directory paths the
            agents are permitted to read source files from. Any path in
            ``files_path`` that does not resolve under one of these directories
            is silently blocked. Leave empty to allow all paths (default).
    """
    session_id = str(uuid.uuid4())
    event_queue: queue.Queue = queue.Queue()
    review_event = threading.Event()

    _sessions[session_id] = {
        "event_queue": event_queue,
        "review_event": review_event,
        "review_result": {},
    }

    files_list = [f.strip() for f in files_path.split(",") if f.strip()]
    allowed_dirs = [d.strip() for d in allowed_read_dirs.split(",") if d.strip()]
    pinned_list = [f.strip() for f in pinned_folders.split(",") if f.strip()]

    # ── Per-run callbacks (captured in closures) ──────────────────────────────

    def on_node_enter(node_name: str, state: SharedState) -> None:
        event_queue.put({"type": "node_start", "node": node_name})

    def on_node_exit(node_name: str, state: SharedState, elapsed_ms: float) -> None:
        event_queue.put({
            "type": "node_complete",
            "node": node_name,
            "elapsed_ms": round(elapsed_ms),
        })

    def human_review_fn(draft: str, state: SharedState) -> tuple[bool, str]:
        reviewer_findings = state.get("reviewer_findings") or {}
        event_queue.put({
            "type": "human_review",
            "draft": draft,
            "reviewer_findings": (
                reviewer_findings if isinstance(reviewer_findings, dict) else {}
            ),
        })
        _sessions[session_id]["review_event"].clear()
        _sessions[session_id]["review_event"].wait(timeout=600)  # 10-min gate
        result = _sessions[session_id].get("review_result", {})
        return result.get("approved", False), result.get("notes", "")

    # ── Graph thread ──────────────────────────────────────────────────────────

    def run_in_thread() -> None:
        try:
            # ── Output sandbox setup ──────────────────────────────────────────
            # Resolve effective output dir: UI param → .env OUTPUT_DIR → none.
            # Create a per-run subdirectory so multiple runs never collide.
            # file_writer is passed into the graph and captured by both the
            # writer agent (proactive file creation) and artifact_writer_node
            # (auto-writes output.md after every approved run).
            effective_output_dir = output_dir.strip() or _default_output_dir
            session_file_writer: FileWriter | None = None
            sandbox_root_str = ""
            if effective_output_dir:
                sandbox_path = Path(effective_output_dir) / f"run_{session_id[:8]}"
                session_file_writer = FileWriter(sandbox_path)
                sandbox_root_str = session_file_writer.sandbox_root
                print(f"[server] Output sandbox: {sandbox_root_str}")

            # ── Read-path sandboxing ──────────────────────────────────────────
            # If the caller supplied allowed_read_dirs, reject any files_path
            # entries that don't resolve under one of the permitted directories.
            validated_files = files_list
            if allowed_dirs:
                resolved_allowed = [Path(d).resolve() for d in allowed_dirs]
                validated_files = []
                for f in files_list:
                    file_resolved = Path(f).resolve()
                    if any(
                        str(file_resolved).startswith(str(allowed))
                        for allowed in resolved_allowed
                    ):
                        validated_files.append(f)
                    else:
                        print(
                            f"[server] Blocked read (outside allowed_read_dirs): {f}"
                        )

            graph = make_graph(
                on_node_enter=on_node_enter,
                on_node_exit=on_node_exit,
                human_review_fn=human_review_fn,
                file_writer=session_file_writer,
            )

            jt_requested, jt_mode = detect_jt_request(
                task=task, cli_jt=jt_enabled, cli_mode=None
            )
            file_read_result = load_local_files(validated_files)

            # Inject vault context into the run state so the CoS run() and
            # Researcher both benefit from the same two-tier vault map.
            vault_run_ctx = ""
            if _vault_session_loader and _vault_session_loader.available:
                vault_run_ctx = _vault_session_loader.render_for_prompt(
                    pinned_folders=pinned_list
                )

            # Hint the Chief of Staff toward the requested output format
            enhanced_task = task
            if output_format and output_format not in (
                "Chat", "Let CoS decide", "Determine during planning"
            ):
                enhanced_task = (
                    f"{task}\n\n[Preferred output format: {output_format}]"
                )

            # Carry project memory across runs within the same browser session
            prior_memory = _session_memory.get(mem_session or session_id, empty_project_memory())

            initial_state: SharedState = {
                "user_task": enhanced_task,
                "status": "received",
                "dry_run": False,
                "debug": False,
                "web_search_enabled": web_search,
                "jt_requested": jt_requested,
                "jt_mode": jt_mode,
                "dev_pod_requested": branch == "build",
                "advisor_pod_requested": branch == "brainstorm",
                "jt_feedback": [],
                "jt_rewrite": None,
                "jt_findings": None,
                "current_run": {
                    "objective": "",
                    "deliverable_type": "",
                    "open_questions": [],
                    "latest_draft": "",
                    "latest_approved_output": "",
                },
                "project_memory": prior_memory,
                "files_requested": file_read_result["files_requested"],
                "files_read": file_read_result["files_read"],
                "files_skipped": file_read_result["files_skipped"],
                "skip_reasons": file_read_result["skip_reasons"],
                "model_metadata": {
                    "file_contents": file_read_result["file_contents"],
                    "vault_context": vault_run_ctx,
                },
                # File output sandboxing
                "output_dir": output_dir.strip(),
                "sandbox_root": sandbox_root_str,
                "files_created": [],
                "allowed_read_dirs": allowed_dirs,
            }

            result = graph.invoke(initial_state)

            # Persist memory for next run
            _session_memory[mem_session or session_id] = normalize_project_memory(
                result.get("project_memory")
            )

            files_created = result.get("files_created", [])
            if files_created:
                print(f"[server] Files created this run ({len(files_created)}): {files_created}")

            event_queue.put({
                "type": "final",
                "output": result.get("final_output", ""),
                "status": result.get("status", ""),
                "execution_path": (
                    result.get("model_metadata", {}).get("execution_path", [])
                ),
                "node_timings_ms": (
                    result.get("model_metadata", {}).get("node_timings_ms", {})
                ),
                "files_created": files_created,
                "sandbox_root": result.get("sandbox_root", ""),
            })

        except Exception as exc:  # noqa: BLE001
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            event_queue.put(None)  # sentinel — tells the SSE generator to close

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()

    # ── SSE generator ─────────────────────────────────────────────────────────

    def event_generator():
        # First event: session_id so the browser can send /approve back
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        while True:
            try:
                item = event_queue.get(timeout=25)  # heartbeat every 25 s
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                continue

            if item is None:  # sentinel → done
                break
            yield f"data: {json.dumps(item)}\n\n"

        _sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Dev entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=True)
