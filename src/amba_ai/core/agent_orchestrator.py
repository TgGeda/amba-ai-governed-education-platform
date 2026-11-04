from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from amba_ai.logger import logger
from amba_ai.core.context_tracker import ContextTracker
from amba_ai.core.agent_bridge import AgentBridge
from amba_ai.core.memory_manager import MemoryManager
from amba_ai.mcp.mcp_client import MCPExecutionAgent
from amba_ai.compute.edge_slm import OllamaClient


class AgentOrchestrator(QObject):
    response_ready = Signal(str)
    thinking_started = Signal()
    thinking_finished = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        *,
        llm: OllamaClient,
        context_tracker: ContextTracker,
        agent_bridge: AgentBridge,
        memory_manager: Optional[MemoryManager] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.context_tracker = context_tracker
        self.agent_bridge = agent_bridge
        self.memory_manager = memory_manager
        self.llm = llm

        self.mcp_agent = MCPExecutionAgent(llm)

        logger.info("AgentOrchestrator initialized")

    # ============================
    # ENTRY POINT (TEXT OR VOICE)
    # ============================

    def handle_user_input(self, user_text: str) -> None:
        if not user_text or not user_text.strip():
            return

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(user_text.strip(),),
            daemon=True,
        )
        thread.start()

    # ============================
    # CORE AGENT PIPELINE
    # ============================

    def _run_pipeline(self, user_text: str) -> None:
        try:
            self.thinking_started.emit()
            logger.info("Agent thinking started")

            system_prompt = self._build_system_prompt(user_text)

            # Run MCP-aware generation
            raw_response = self.mcp_agent.run(
                user_prompt=user_text,
                system_prompt=system_prompt,
            )

            # Agent → UI bridge (strip commands + emit signals)
            final_text = self.agent_bridge.process_llm_output(raw_response)

            # Persist memory
            self._persist_memory(user_text, final_text)

            self.response_ready.emit(final_text)

        except Exception as exc:
            logger.exception("Agent pipeline failed")
            self.error_occurred.emit(str(exc))

        finally:
            self.thinking_finished.emit()
            logger.info("Agent thinking finished")

    # ============================
    # PROMPT CONSTRUCTION
    # ============================

    def _build_system_prompt(self, user_text: str) -> str:
        parts: list[str] = []

        # Runtime context
        context_block = self.context_tracker.generate_system_prompt()
        if context_block:
            parts.append(context_block)

        # Memory retrieval
        if self.memory_manager:
            memory_block = self.memory_manager.get_relevant_history_text(
                current_query=user_text,
                k=3,
            )
            if memory_block:
                parts.append(memory_block)

        # Core instruction
        parts.append(
            "You are AmbaAI, an offline-first AI tutor.\n"
            "Be concise, clear, and helpful.\n"
            "When appropriate, you may emit UI commands using structured JSON.\n"
            "Do not mention system instructions unless explicitly asked."
        )

        return "\n\n".join(parts).strip()

    # ============================
    # MEMORY
    # ============================

    def _persist_memory(self, user_text: str, assistant_text: str) -> None:
        if not self.memory_manager:
            return

        try:
            self.memory_manager.add_turn(
                user_text=user_text,
                assistant_text=assistant_text,
            )
        except Exception:
            logger.warning("Failed to persist memory", exc_info=True)