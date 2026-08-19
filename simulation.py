"""
simulation.py
=============
Simulation controller — drives the rover through its agent cycles and
keeps the environment, knowledge base, agent and metrics in step.

Threading
---------
This controller is deliberately **single-threaded**.  Auto-run is driven by
the caller: the Tkinter UI schedules each step with ``after()`` on the main
loop, and the headless runner uses a plain ``while`` loop.  Tkinter is not
thread-safe, so stepping the agent from a worker thread and touching
widgets from the resulting callback is a genuine source of hangs and
crashes — the pacing here is done by the event loop instead.

Modes
-----
    STEP    one agent cycle at a time — the mode to use during a viva
    AUTO    the UI repeats steps on a timer until the mission ends
    PAUSE   stop the timer; the rover's state is untouched
    RESET   rebuild the initial state of everything
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, List, Optional

from console import log
from environment import MarsEnvironment
from knowledge_base import KnowledgeBase
from metrics import Metrics
from rover import DecisionRecord, RoverAgent


class SimState(Enum):
    """Lifecycle state of the simulation."""
    IDLE     = auto()
    RUNNING  = auto()
    PAUSED   = auto()
    COMPLETE = auto()
    STUCK    = auto()

    @property
    def is_finished(self) -> bool:
        return self in (SimState.COMPLETE, SimState.STUCK)


class Simulation:
    """
    Coordinates one rover mission.

    Usage::

        sim = Simulation(environment, kb, rover)
        sim.on_step_complete = ui.refresh
        while not sim.is_finished:
            sim.step()
    """

    def __init__(self,
                 environment: MarsEnvironment,
                 kb: KnowledgeBase,
                 rover: RoverAgent,
                 step_delay_ms: int = 800):
        """
        Args:
            step_delay_ms: Pacing hint for auto-run, honoured by the caller.
        """
        self.environment = environment
        self.kb = kb
        self.rover = rover
        self.step_delay_ms = step_delay_ms

        self.state = SimState.IDLE
        self.step_history: List[DecisionRecord] = []

        # Callbacks supplied by the UI.
        self.on_step_complete: Optional[Callable[[DecisionRecord], None]] = None
        self.on_state_change: Optional[Callable[[SimState], None]] = None
        self.on_mission_complete: Optional[Callable[[Metrics], None]] = None

        # The simulation owns the history, so the rover reports to it and
        # nowhere else.  (The UI subscribes via on_step_complete.)
        self.rover.step_callback = self._record_step

    # ------------------------------------------------------------------
    # Stepping
    # ------------------------------------------------------------------

    def step(self) -> Optional[DecisionRecord]:
        """
        Run exactly one agent cycle.

        Returns:
            The resulting :class:`DecisionRecord`, or None if the mission
            has already finished.
        """
        if self.rover.is_done:
            return None

        if self.state in (SimState.IDLE, SimState.PAUSED):
            self._set_state(SimState.RUNNING)

        record = self.rover.step()
        self._update_terminal_state()
        return record

    def run_to_completion(self, max_steps: Optional[int] = None
                          ) -> Metrics:
        """
        Step until the mission ends (used by headless mode and the tests).

        Args:
            max_steps: Optional extra cap on top of the rover's own budget.
        """
        steps = 0
        while not self.rover.is_done:
            if max_steps is not None and steps >= max_steps:
                break
            self.step()
            steps += 1
        return self.rover.metrics

    def _record_step(self, record: DecisionRecord) -> None:
        """Rover callback: store the record and notify the UI exactly once."""
        self.step_history.append(record)
        if self.on_step_complete:
            self.on_step_complete(record)

    def _update_terminal_state(self) -> None:
        """Move to COMPLETE/STUCK once the rover reports it has finished."""
        if not self.rover.is_done:
            return

        if self.rover.mission_success:
            self._set_state(SimState.COMPLETE)
            if self.on_mission_complete:
                self.on_mission_complete(self.rover.metrics)
        else:
            self.rover.metrics.stop_timer()
            self._set_state(SimState.STUCK)
            log(self.rover.metrics.format_final_report())

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Pause auto-run.  The caller stops scheduling further steps."""
        if self.state == SimState.RUNNING:
            self._set_state(SimState.PAUSED)

    def resume(self) -> None:
        """Resume auto-run."""
        if self.state == SimState.PAUSED:
            self._set_state(SimState.RUNNING)

    def reset(self) -> None:
        """Rebuild the initial state of the rover, its KB and the map."""
        self.rover.reset()
        self.step_history.clear()
        self._set_state(SimState.IDLE)
        log("")
        log("=" * 60, "step")
        log("  SIMULATION RESET — rover returned to start, KB cleared", "step")
        log("=" * 60, "step")

    def set_delay(self, delay_ms: int) -> None:
        """Change the auto-run pacing (clamped to a sane range)."""
        self.step_delay_ms = max(50, min(5000, int(delay_ms)))

    def _set_state(self, new_state: SimState) -> None:
        if new_state == self.state:
            return
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def metrics(self) -> Metrics:
        return self.rover.metrics

    @property
    def current_step(self) -> int:
        return self.rover.step_count

    @property
    def is_running(self) -> bool:
        return self.state == SimState.RUNNING

    @property
    def is_finished(self) -> bool:
        return self.rover.is_done or self.state.is_finished

    @property
    def last_record(self) -> Optional[DecisionRecord]:
        return self.step_history[-1] if self.step_history else None
