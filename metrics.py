"""
metrics.py
==========
Performance metrics for one simulation run.

Reported in three groups:

**Mission**    did the rover succeed, in how many steps, at what path cost
**Reasoning**  how much logical work that required — TELL/ASK operations,
               forward-chaining inferences, resolution steps, models
               enumerated by the checker
**Safety**     how many candidate actions the knowledge base rejected, and
               how many unclassified cells were investigated rather than
               assumed safe

The reasoning counters matter as much as the movement ones: they are the
evidence that the rover's route was produced by inference rather than by a
search algorithm.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Metrics:
    """Quantitative record of a single mission."""

    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None

    # -- Mission --------------------------------------------------------
    moves: int = 0
    path_cost: float = 0.0
    cells_visited: int = 0
    total_steps: int = 0
    mission_success: bool = False

    # -- Reasoning ------------------------------------------------------
    inference_ops: int = 0        # forward-chaining derivations + ASK calls
    resolution_ops: int = 0       # individual resolution rule applications
    model_check_ops: int = 0      # model-checking queries run
    models_enumerated: int = 0    # truth assignments actually evaluated
    tell_ops: int = 0
    ask_ops: int = 0
    perceptions: int = 0

    # -- Safety ---------------------------------------------------------
    unsafe_actions_rejected: int = 0
    investigations: int = 0

    # -- Final KB size --------------------------------------------------
    kb_facts_final: int = 0
    kb_rules_final: int = 0
    kb_clauses_final: int = 0

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    def stop_timer(self) -> None:
        """Freeze the execution timer at mission end."""
        if self.end_time is None:
            self.end_time = time.perf_counter()

    @property
    def execution_time_sec(self) -> float:
        """Wall-clock time from construction to mission end, in seconds."""
        end = self.end_time if self.end_time is not None else time.perf_counter()
        return end - self.start_time

    @property
    def execution_time_ms(self) -> float:
        """Wall-clock time in milliseconds."""
        return self.execution_time_sec * 1000.0

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def format_final_report(self) -> str:
        """The full metrics block printed at mission end."""
        status = "SUCCESS" if self.mission_success else "INCOMPLETE"
        width = 60
        lines = [
            "",
            "=" * width,
            "                  FINAL PERFORMANCE METRICS",
            "=" * width,
            f"  Mission Status:            {status}",
            f"  Execution Time:            {self.execution_time_sec:.3f} sec "
            f"({self.execution_time_ms:.1f} ms)",
            "-" * width,
            "  MISSION",
            f"    Agent Cycles (steps):    {self.total_steps}",
            f"    Moves Made:              {self.moves}",
            f"    Investigations:          {self.investigations}",
            f"    Path Cost:               {self.path_cost:.1f}",
            f"    Cells Visited:           {self.cells_visited}",
            "-" * width,
            "  REASONING",
            f"    TELL Operations:         {self.tell_ops}",
            f"    ASK Operations:          {self.ask_ops}",
            f"    Inference Operations:    {self.inference_ops}",
            f"    Resolution Operations:   {self.resolution_ops}",
            f"    Model-Checking Queries:  {self.model_check_ops}",
            f"    Models Enumerated:       {self.models_enumerated}",
            f"    Sensor Perceptions:      {self.perceptions}",
            "-" * width,
            "  SAFETY",
            f"    Unsafe Actions Rejected: {self.unsafe_actions_rejected}",
            "-" * width,
            "  FINAL KNOWLEDGE BASE",
            f"    Facts:                   {self.kb_facts_final}",
            f"    Rules:                   {self.kb_rules_final}",
            f"    CNF Clauses:             {self.kb_clauses_final}",
            "=" * width,
        ]
        return "\n".join(lines)

    def format_compact(self) -> str:
        """One-line summary for the UI status bar."""
        return (f"Moves:{self.moves} | Cost:{self.path_cost:.1f} | "
                f"Inferences:{self.inference_ops} | "
                f"Resolutions:{self.resolution_ops} | "
                f"Rejected:{self.unsafe_actions_rejected}")

    def to_dict(self) -> dict:
        """Export every metric as a plain dictionary."""
        return {
            "mission_success": self.mission_success,
            "execution_time_sec": round(self.execution_time_sec, 4),
            "total_steps": self.total_steps,
            "moves": self.moves,
            "investigations": self.investigations,
            "path_cost": self.path_cost,
            "cells_visited": self.cells_visited,
            "tell_ops": self.tell_ops,
            "ask_ops": self.ask_ops,
            "inference_ops": self.inference_ops,
            "resolution_ops": self.resolution_ops,
            "model_check_ops": self.model_check_ops,
            "models_enumerated": self.models_enumerated,
            "perceptions": self.perceptions,
            "unsafe_actions_rejected": self.unsafe_actions_rejected,
            "kb_facts_final": self.kb_facts_final,
            "kb_rules_final": self.kb_rules_final,
            "kb_clauses_final": self.kb_clauses_final,
        }
