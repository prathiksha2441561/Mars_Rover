"""
sensors.py
==========
The rover's sensor suite — the **only** bridge between the environment's
ground truth and the rover's knowledge base.

    Environment cell → Sensor → PerceptionEvent → Propositions → TELL(KB)

Sensors provided
----------------
============================  =====================================
Terrain scanner (long range)  Classifies each adjacent cell, but
                              returns UNKNOWN for terrain it cannot
                              resolve from a distance.
Hazard sensor                 Produces ``PerceiveHazard_x_y``.
Radiation sensor              Produces ``PerceiveRadiation_x_y``.
Goal sensor                   Produces ``Goal_x_y``.
Investigation probe           Close-range sweep that resolves ONE
                              unknown cell to its true terrain type.
                              Costs an action — see Rule 6.
============================  =====================================

Note the asymmetry that makes unknown terrain meaningful: the long-range
scanner reports *that* a cell is unclassified, the probe reports *what* it
is.  The rover therefore has to decide whether a cell is worth the cost of
investigating, which is precisely what Rule 6 (Unknown → Investigate)
licenses it to do.

Sensors here are noise-free.  Real rover sensors are not; see the
"Limitations" section of the README.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from environment import CellType, MarsEnvironment


# ---------------------------------------------------------------------------
# Perception event
# ---------------------------------------------------------------------------

@dataclass
class PerceptionEvent:
    """
    One sensor reading, already translated into propositional form.

    Attributes:
        cell:         The (x, y) coordinate perceived.
        cell_type:    The terrain classification the sensor reports.
        propositions: ``(symbol, is_positive)`` pairs to TELL the KB.
        description:  Human-readable line for the live log.
        sensor:       Which sensor produced the reading.
        is_new:       True the first time this cell is classified.
    """
    cell: Tuple[int, int]
    cell_type: CellType
    propositions: List[Tuple[str, bool]] = field(default_factory=list)
    description: str = ""
    sensor: str = "TERRAIN"
    is_new: bool = True

    @property
    def status(self) -> str:
        """The KB status keyword implied by this reading."""
        if self.cell_type in (CellType.SAFE, CellType.START):
            return "SAFE"
        if self.cell_type == CellType.GOAL:
            return "GOAL"
        return self.cell_type.value

    def __str__(self) -> str:
        return f"[{self.sensor}] {self.description}"


# ---------------------------------------------------------------------------
# Sensor system
# ---------------------------------------------------------------------------

class SensorSystem:
    """
    Simulated sensor suite.

    This class is the *only* place allowed to read the environment.  The
    rover holds one of these and receives nothing but PerceptionEvents.
    """

    def __init__(self, environment: MarsEnvironment):
        self.environment = environment
        self._perception_count = 0
        self._investigation_count = 0
        # Cells already classified, so repeat scans can be reported as
        # "already known" instead of re-telling the KB the same facts.
        self._classified: set = set()

    # ------------------------------------------------------------------
    # Long-range perception
    # ------------------------------------------------------------------

    def perceive_current_cell(self, x: int, y: int) -> PerceptionEvent:
        """Sense the cell the rover currently occupies."""
        event = self._scan(x, y)
        event.description = (f"Occupying ({x},{y}) — terrain: "
                             f"{event.cell_type.value}")
        event.sensor = "TERRAIN"
        return event

    def perceive_adjacent_cells(self, x: int, y: int) -> List[PerceptionEvent]:
        """Sense all in-bounds neighbours of (x, y)."""
        return [self._scan(nx, ny)
                for nx, ny in self.environment.get_adjacent(x, y)]

    def perceive_all(self, x: int, y: int) -> List[PerceptionEvent]:
        """Full sweep: the current cell followed by every neighbour."""
        return [self.perceive_current_cell(x, y)] + \
               self.perceive_adjacent_cells(x, y)

    # ------------------------------------------------------------------
    # Close-range investigation (the INVESTIGATE action)
    # ------------------------------------------------------------------

    def investigate(self, x: int, y: int) -> PerceptionEvent:
        """
        Spend a close-range sensor sweep to classify one unknown cell.

        This is the perception half of the INVESTIGATE action: it resolves
        ``Unknown_x_y`` into ``Safe_x_y``, ``Hazard_x_y`` or
        ``Radiation_x_y`` — after which Rules 1–3 determine whether the
        cell may be entered.
        """
        self._investigation_count += 1
        self._perception_count += 1

        revealed = self.environment.investigate_cell(x, y)
        self._classified.add((x, y))

        descriptions = {
            CellType.HAZARD:    f"PROBE: close-range sweep of ({x},{y}) "
                                f"reveals HAZARD",
            CellType.RADIATION: f"PROBE: close-range sweep of ({x},{y}) "
                                f"reveals RADIATION",
            CellType.SAFE:      f"PROBE: close-range sweep of ({x},{y}) "
                                f"confirms SAFE terrain",
        }

        return PerceptionEvent(
            cell=(x, y),
            cell_type=revealed,
            propositions=self._to_propositions(x, y, revealed),
            description=descriptions.get(
                revealed, f"PROBE: ({x},{y}) is {revealed.value}"),
            sensor="PROBE",
            is_new=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scan(self, x: int, y: int) -> PerceptionEvent:
        """Long-range scan of a single cell."""
        self._perception_count += 1
        cell_type = self.environment.get_cell(x, y)

        is_new = (x, y) not in self._classified
        if cell_type != CellType.UNKNOWN:
            self._classified.add((x, y))

        sensor, description = self._describe(x, y, cell_type)

        return PerceptionEvent(
            cell=(x, y),
            cell_type=cell_type,
            propositions=self._to_propositions(x, y, cell_type),
            description=description,
            sensor=sensor,
            is_new=is_new)

    @staticmethod
    def _describe(x: int, y: int, cell_type: CellType) -> Tuple[str, str]:
        """Return (sensor_name, description) for a reading."""
        table = {
            CellType.HAZARD:    ("HAZARD",
                                 f"HAZARD SENSOR: hazard signal detected at "
                                 f"({x},{y})"),
            CellType.RADIATION: ("RADIATION",
                                 f"RADIATION SENSOR: radiation detected at "
                                 f"({x},{y})"),
            CellType.SAFE:      ("TERRAIN",
                                 f"TERRAIN SENSOR: safe terrain at ({x},{y})"),
            CellType.START:     ("TERRAIN",
                                 f"TERRAIN SENSOR: start position ({x},{y}), "
                                 f"safe terrain"),
            CellType.UNKNOWN:   ("TERRAIN",
                                 f"TERRAIN SENSOR: ({x},{y}) UNCLASSIFIED — "
                                 f"cannot resolve at range"),
            CellType.GOAL:      ("GOAL",
                                 f"GOAL SENSOR: target detected at ({x},{y})"),
        }
        return table[cell_type]

    @staticmethod
    def _to_propositions(x: int, y: int,
                         cell_type: CellType) -> List[Tuple[str, bool]]:
        """
        Translate a terrain classification into propositional assertions.

        Note what is *absent*: an UNKNOWN reading asserts only
        ``Unknown_x_y``.  It deliberately says nothing about Safe, Hazard
        or Radiation, so Rule 3 cannot fire and the cell stays untraversable
        until it is investigated.  Treating "not known to be dangerous" as
        "safe" is exactly the mistake a knowledge-based agent must not make.
        """
        if cell_type == CellType.HAZARD:
            return [(f"PerceiveHazard_{x}_{y}", True),
                    (f"Safe_{x}_{y}", False),
                    (f"Radiation_{x}_{y}", False),
                    (f"Unknown_{x}_{y}", False)]

        if cell_type == CellType.RADIATION:
            return [(f"PerceiveRadiation_{x}_{y}", True),
                    (f"Safe_{x}_{y}", False),
                    (f"Hazard_{x}_{y}", False),
                    (f"Unknown_{x}_{y}", False)]

        if cell_type in (CellType.SAFE, CellType.START):
            return [(f"Safe_{x}_{y}", True),
                    (f"Hazard_{x}_{y}", False),
                    (f"Radiation_{x}_{y}", False),
                    (f"Unknown_{x}_{y}", False)]

        if cell_type == CellType.GOAL:
            return [(f"Goal_{x}_{y}", True),
                    (f"Safe_{x}_{y}", True),
                    (f"Hazard_{x}_{y}", False),
                    (f"Radiation_{x}_{y}", False),
                    (f"Unknown_{x}_{y}", False)]

        # UNKNOWN — the only thing known is that nothing is known.
        return [(f"Unknown_{x}_{y}", True)]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def direction_label(from_pos: Tuple[int, int],
                        to_pos: Tuple[int, int]) -> str:
        """Human-readable direction between two adjacent cells."""
        dx = to_pos[0] - from_pos[0]
        dy = to_pos[1] - from_pos[1]
        return {(1, 0): "RIGHT", (-1, 0): "LEFT",
                (0, -1): "UP", (0, 1): "DOWN"}.get((dx, dy), "UNKNOWN")

    def get_direction_label(self, from_pos: Tuple[int, int],
                            to_pos: Tuple[int, int]) -> str:
        """Instance-method alias of :meth:`direction_label`."""
        return self.direction_label(from_pos, to_pos)

    def _sense_cell(self, x: int, y: int) -> PerceptionEvent:
        """Alias of :meth:`_scan` (kept for external callers/tests)."""
        return self._scan(x, y)

    def check_goal(self, x: int, y: int) -> bool:
        """Goal sensor: is (x, y) the target?"""
        return (x, y) == self.environment.goal_pos

    def reset(self) -> None:
        """Clear sensor history (used when the simulation resets)."""
        self._perception_count = 0
        self._investigation_count = 0
        self._classified.clear()

    @property
    def perception_count(self) -> int:
        return self._perception_count

    @property
    def investigation_count(self) -> int:
        return self._investigation_count
