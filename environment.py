"""
environment.py
==============
The Mars environment — **ground truth**.

    ENVIRONMENT STATE   ≠   ROVER KNOWLEDGE BASE

This module knows the true terrain of every cell.  The rover does not.
The only channel between the two is :mod:`sensors`, which converts terrain
into perceptions, which the rover then TELLs its knowledge base.  Nothing
in :mod:`rover` may call :meth:`MarsEnvironment.get_cell` directly — that
would be reading the map instead of perceiving it, and the agent would no
longer be knowledge-based.

Unknown terrain
---------------
A cell marked ``?`` is **unclassified from a distance**: the rover's
long-range terrain scanner cannot tell what it is.  Underneath, the
environment holds the cell's *hidden true type* (safe, hazard or
radiation).  That hidden type is revealed only when the rover spends an
INVESTIGATE action on the cell — a close-range sensor sweep.  This is what
makes ``Unknown_x_y`` a genuine epistemic state rather than a terrain
colour, and what gives Rule 6 (Unknown → Investigate) something to do.

Map legend
----------
    S  start          .  safe terrain
    G  goal           H  hazard
    ?  unknown        R  radiation zone
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Cell types
# ---------------------------------------------------------------------------

class CellType(Enum):
    """Terrain classification of a grid cell."""
    SAFE      = "SAFE"
    UNKNOWN   = "UNKNOWN"
    HAZARD    = "HAZARD"
    RADIATION = "RADIATION"
    START     = "START"
    GOAL      = "GOAL"

    @property
    def is_dangerous(self) -> bool:
        """True for terrain the rover must never enter."""
        return self in (CellType.HAZARD, CellType.RADIATION)


# ---------------------------------------------------------------------------
# Default deterministic map (7 × 7)
# ---------------------------------------------------------------------------
#
# Indexed as MAP[row][col] == MAP[y][x], with (0,0) at the top-left.
#
# The map is designed so a single run demonstrates every behaviour the
# project needs to show, in a readable order:
#
#   * (1,0) is a hazard directly east of the start, so the rover's very
#     first step must reject its preferred direction on logical grounds
#     (Rule 1) before it has moved at all.
#   * (0,3) is radiation and (0,5) a hazard, closing the left edge.  The
#     rover cannot simply hug the border to the goal — it has to work
#     through the middle of the map, where the interesting terrain is.
#   * The four ? cells sit on the diagonal, i.e. on the most direct route.
#     The rover therefore has to INVESTIGATE them rather than detour
#     around everything it cannot classify.
#   * (1,1), (2,2) and (4,4) hide SAFE terrain: investigating them earns
#     genuine shortcuts, so information has visible value.
#   * (3,3) hides a HAZARD.  Investigating turns Unknown_3_3 into a danger
#     fact, Rule 1 fires, and the rover must re-plan mid-route — the
#     clearest demonstration in the run that its behaviour is driven by
#     what the knowledge base entails.
#   * A route to (6,6) through confirmed-safe terrain always exists; the
#     constructor asserts this, so the demonstration cannot silently fail.

DEFAULT_MAP_STRINGS: List[List[str]] = [
    # x:  0    1    2    3    4    5    6
    ["S", "H", ".", ".", "R", ".", "."],   # y = 0
    [".", "?", "H", ".", ".", "H", "."],   # y = 1
    [".", ".", "?", "R", ".", ".", "."],   # y = 2
    ["R", ".", ".", "?", "H", ".", "."],   # y = 3
    [".", "H", ".", ".", "?", ".", "."],   # y = 4
    ["H", ".", "R", ".", ".", "H", "."],   # y = 5
    [".", ".", ".", "H", ".", ".", "G"],   # y = 6
]

# What each ``?`` cell really is.  The rover learns this only by spending
# an INVESTIGATE action; nothing outside :mod:`sensors` may read it.
DEFAULT_HIDDEN_TYPES: Dict[Tuple[int, int], CellType] = {
    (1, 1): CellType.SAFE,      # investigating opens a shortcut
    (2, 2): CellType.SAFE,      # investigating opens a shortcut
    (3, 3): CellType.HAZARD,    # investigating reveals danger → re-plan
    (4, 4): CellType.SAFE,      # investigating opens a shortcut
}

_MAP_CHAR_TO_CELL = {
    "S": CellType.START,
    "G": CellType.GOAL,
    ".": CellType.SAFE,
    "H": CellType.HAZARD,
    "R": CellType.RADIATION,
    "?": CellType.UNKNOWN,
}

_CELL_TO_CHAR = {
    CellType.SAFE: ".",
    CellType.UNKNOWN: "?",
    CellType.HAZARD: "H",
    CellType.RADIATION: "R",
    CellType.START: "S",
    CellType.GOAL: "G",
}


# ---------------------------------------------------------------------------
# MarsEnvironment
# ---------------------------------------------------------------------------

class MarsEnvironment:
    """
    The ground-truth Mars grid.

    Attributes:
        width, height:  Grid dimensions.
        start_pos:      (x, y) where the rover begins.
        goal_pos:       (x, y) target coordinate.
        grid:           2-D list of :class:`CellType`, indexed ``grid[y][x]``.
        hidden_types:   True terrain beneath each UNKNOWN cell.
    """

    def __init__(self,
                 use_random: bool = False,
                 seed: int = 42,
                 random_size: int = 7):
        """
        Args:
            use_random:  Generate a random (but seeded and solvable) map.
            seed:        Seed for random generation.
            random_size: Side length of the random grid.
        """
        self.hidden_types: Dict[Tuple[int, int], CellType] = {}
        self.is_random = use_random
        self.seed = seed

        if use_random:
            self._init_random(seed, random_size)
        else:
            self._init_default()

        # Cells whose UNKNOWN status has been resolved by investigation.
        self._revealed: Set[Tuple[int, int]] = set()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _init_default(self) -> None:
        """Build the deterministic demonstration map."""
        self.height = len(DEFAULT_MAP_STRINGS)
        self.width = len(DEFAULT_MAP_STRINGS[0])
        self.grid: List[List[CellType]] = []
        self.start_pos: Tuple[int, int] = (0, 0)
        self.goal_pos: Tuple[int, int] = (self.width - 1, self.height - 1)

        for y, row in enumerate(DEFAULT_MAP_STRINGS):
            grid_row: List[CellType] = []
            for x, char in enumerate(row):
                cell = _MAP_CHAR_TO_CELL.get(char, CellType.SAFE)
                if cell == CellType.START:
                    self.start_pos = (x, y)
                elif cell == CellType.GOAL:
                    self.goal_pos = (x, y)
                grid_row.append(cell)
            self.grid.append(grid_row)

        self.hidden_types = dict(DEFAULT_HIDDEN_TYPES)
        self._validate_hidden_types()

        if not self._path_exists():
            raise RuntimeError(
                "Default map is unsolvable — the demonstration map must "
                "always have a route through confirmed-safe terrain.")

    def _init_random(self, seed: int, size: int) -> None:
        """Generate a random map that is seeded and guaranteed solvable."""
        import random
        rng = random.Random(seed)

        self.width = self.height = size
        self.start_pos = (0, 0)
        self.goal_pos = (size - 1, size - 1)
        self.grid = [[CellType.SAFE] * size for _ in range(size)]

        total = size * size
        counts = {
            CellType.HAZARD:    max(3, total // 8),
            CellType.RADIATION: max(2, total // 12),
            CellType.UNKNOWN:   max(3, total // 10),
        }

        occupied = {self.start_pos, self.goal_pos}
        for cell_type, count in counts.items():
            placed = 0
            attempts = 0
            while placed < count and attempts < total * 10:
                attempts += 1
                x, y = rng.randrange(size), rng.randrange(size)
                if (x, y) in occupied:
                    continue
                self.grid[y][x] = cell_type
                occupied.add((x, y))
                placed += 1
                if cell_type == CellType.UNKNOWN:
                    # Bias hidden terrain towards safe so random maps stay
                    # solvable, but keep real danger behind some of them.
                    self.hidden_types[(x, y)] = rng.choice(
                        [CellType.SAFE, CellType.SAFE,
                         CellType.HAZARD, CellType.RADIATION])

        sx, sy = self.start_pos
        gx, gy = self.goal_pos
        self.grid[sy][sx] = CellType.START
        self.grid[gy][gx] = CellType.GOAL

        if not self._path_exists():
            self._force_path()

    def _validate_hidden_types(self) -> None:
        """Every UNKNOWN cell must have a hidden true type, and vice versa."""
        unknown_cells = {
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.grid[y][x] == CellType.UNKNOWN
        }
        missing = unknown_cells - set(self.hidden_types)
        if missing:
            raise ValueError(
                f"UNKNOWN cells without a hidden true type: {sorted(missing)}")
        extra = set(self.hidden_types) - unknown_cells
        if extra:
            raise ValueError(
                f"Hidden types declared for non-UNKNOWN cells: {sorted(extra)}")

    # ------------------------------------------------------------------
    # Solvability
    # ------------------------------------------------------------------

    def _path_exists(self) -> bool:
        """
        Is the goal reachable using only terrain the rover could ever
        confirm safe?

        Unknown cells count as passable *only* if their hidden type is
        safe, because that is exactly what investigation would reveal.
        This check exists purely to validate map design — the rover never
        calls it.
        """
        queue = deque([self.start_pos])
        seen = {self.start_pos}

        while queue:
            position = queue.popleft()
            if position == self.goal_pos:
                return True
            for neighbour in self.get_adjacent(*position):
                if neighbour in seen:
                    continue
                if self._is_traversable_truth(neighbour):
                    seen.add(neighbour)
                    queue.append(neighbour)
        return False

    def _is_traversable_truth(self, position: Tuple[int, int]) -> bool:
        """Ground-truth traversability, resolving UNKNOWN to its hidden type."""
        x, y = position
        cell = self.grid[y][x]
        if cell == CellType.UNKNOWN:
            cell = self.hidden_types.get(position, CellType.SAFE)
        return not cell.is_dangerous

    def _force_path(self) -> None:
        """Clear a staircase route to the goal so a random map stays solvable."""
        x, y = self.start_pos
        gx, gy = self.goal_pos
        while (x, y) != (gx, gy):
            if x < gx:
                x += 1
            elif y < gy:
                y += 1
            if (x, y) != (gx, gy):
                self.grid[y][x] = CellType.SAFE
                self.hidden_types.pop((x, y), None)

    # ------------------------------------------------------------------
    # Queries (sensors only)
    # ------------------------------------------------------------------

    def get_cell(self, x: int, y: int) -> CellType:
        """
        The terrain type a **remote scan** reports for (x, y).

        UNKNOWN cells stay UNKNOWN until investigated.
        """
        if not self.is_in_bounds(x, y):
            raise ValueError(f"Coordinate ({x},{y}) is out of bounds")
        cell = self.grid[y][x]
        if cell == CellType.UNKNOWN and (x, y) in self._revealed:
            return self.hidden_types[(x, y)]
        return cell

    def investigate_cell(self, x: int, y: int) -> CellType:
        """
        Close-range sensor sweep: permanently resolve an UNKNOWN cell to its
        true terrain type.

        Called only by :class:`sensors.SensorSystem` when the rover spends
        an INVESTIGATE action.  Returns the revealed terrain type (or the
        existing type for a cell that was never unknown).
        """
        if not self.is_in_bounds(x, y):
            raise ValueError(f"Coordinate ({x},{y}) is out of bounds")

        if self.grid[y][x] == CellType.UNKNOWN:
            self._revealed.add((x, y))
            return self.hidden_types[(x, y)]
        return self.grid[y][x]

    def is_traversable(self, x: int, y: int) -> bool:
        """
        Ground-truth traversability of (x, y) — ``True`` unless the true
        terrain (resolving UNKNOWN to its hidden type) is dangerous.

        This is a *test/tooling* helper for checking map design; the rover
        itself must never call it, since that would be reading the map
        instead of reasoning about perceptions.
        """
        return self._is_traversable_truth((x, y))

    def is_unknown(self, x: int, y: int) -> bool:
        """True if (x, y) is unclassified and has not yet been investigated."""
        return (self.grid[y][x] == CellType.UNKNOWN
                and (x, y) not in self._revealed)

    def is_in_bounds(self, x: int, y: int) -> bool:
        """Is (x, y) inside the grid?"""
        return 0 <= x < self.width and 0 <= y < self.height

    def get_adjacent(self, x: int, y: int) -> List[Tuple[int, int]]:
        """The in-bounds 4-connected neighbours of (x, y), UP/DOWN/LEFT/RIGHT."""
        candidates = [(x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)]
        return [c for c in candidates if self.is_in_bounds(*c)]

    def reset_revelations(self) -> None:
        """Re-hide every investigated cell (used when the simulation resets)."""
        self._revealed.clear()

    # ------------------------------------------------------------------
    # Display helpers (console only — never used for decisions)
    # ------------------------------------------------------------------

    def print_grid(self,
                   rover_pos: Optional[Tuple[int, int]] = None,
                   visited: Optional[Set[Tuple[int, int]]] = None) -> None:
        """Print the ground-truth map to the console."""
        from console import log

        log(f"\n  MARS ENVIRONMENT — GROUND TRUTH ({self.width}×{self.height})")
        log("     " + "  ".join(f"{x}" for x in range(self.width)))
        for y in range(self.height):
            row = f"  {y}  "
            for x in range(self.width):
                if rover_pos and (x, y) == rover_pos:
                    row += " @ "
                elif visited and (x, y) in visited:
                    row += " * "
                else:
                    row += f" {_CELL_TO_CHAR[self.grid[y][x]]} "
            log(row)
        log("     S=start  G=goal  .=safe  H=hazard  R=radiation  ?=unknown")

    def get_map_description(self) -> str:
        """A short textual summary of the map for the startup banner."""
        def cells_of(cell_type: CellType) -> List[Tuple[int, int]]:
            return [(x, y)
                    for y in range(self.height)
                    for x in range(self.width)
                    if self.grid[y][x] == cell_type]

        unknown = cells_of(CellType.UNKNOWN)
        hidden_summary = ", ".join(
            f"{cell}→hidden" for cell in unknown) or "none"

        return "\n".join([
            f"Mars Grid:       {self.width}×{self.height}"
            f"{'  (random, seed ' + str(self.seed) + ')' if self.is_random else '  (default demonstration map)'}",
            f"Start:           {self.start_pos}",
            f"Goal:            {self.goal_pos}",
            f"Hazards:         {cells_of(CellType.HAZARD)}",
            f"Radiation zones: {cells_of(CellType.RADIATION)}",
            f"Unknown cells:   {unknown}",
            f"                 (true terrain concealed until investigated: "
            f"{hidden_summary})",
        ])
