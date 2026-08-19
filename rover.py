"""
rover.py
========
The Autonomous Mars Rover — a Propositional Logic Knowledge-Based Agent.

The agent cycle
---------------
Every call to :meth:`RoverAgent.step` runs one complete cycle::

    PERCEIVE              sensors read the current cell and its neighbours
      → TELL(KB)          perceptions become propositions in the KB
      → INFER             forward chaining derives new facts (Modus Ponens)
      → ASK(KB)           each candidate action is queried for entailment
      → DECIDE            unsafe actions are rejected on logical grounds
      → ACT               move, or investigate unclassified terrain
      → SUCCESSOR STATE   the At_x_y fluent is updated
      → repeat

What makes this a knowledge-based agent
---------------------------------------
The rover never reads the map.  It holds no set of "known hazards", no
distance field, no precomputed route.  Its entire model of Mars is the
propositional knowledge base, and a move happens **only** when

    KB ⊨ CanMove_x_y

is established by the inference engine.  The Manhattan-distance heuristic
appears in exactly one place — choosing between candidates that logic has
*already* certified as safe.  It can never license a move that the KB does
not entail, and removing it would change which safe route is taken, not
whether unsafe cells are avoided.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set, Tuple

from console import log
from environment import CellType, MarsEnvironment
from knowledge_base import KnowledgeBase
from metrics import Metrics
from sensors import PerceptionEvent, SensorSystem

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "UP":    (0, -1),
    "DOWN":  (0,  1),
    "LEFT":  (-1, 0),
    "RIGHT": (1,  0),
}

# Action costs (see the Path Cost section of the README)
MOVE_COST = 1.0
INVESTIGATE_COST = 0.5      # a sensor sweep is cheaper than a move
MAX_STEPS_FACTOR = 6        # step budget = grid area × this


# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------

class DecisionRecord:
    """
    Everything that happened in one agent cycle.

    Consumed by the UI's status, knowledge-base and "why did the rover
    move?" panels, and retained as the simulation history.
    """

    def __init__(self, step: int, position: Tuple[int, int]):
        self.step = step
        self.position = position
        self.perceptions: List[str] = []
        self.kb_tells: List[str] = []
        self.forward_inferences: List[str] = []
        self.candidates_evaluated: List[Dict] = []
        self.action_type: str = ""          # MOVE | INVESTIGATE | BACKTRACK
        self.chosen_action: Optional[str] = None
        self.chosen_target: Optional[Tuple[int, int]] = None
        self.successor_state: Optional[Tuple[int, int]] = None
        self.path_cost: float = 0.0
        self.explanation: str = ""
        self.rejected_count: int = 0
        self.mission_complete: bool = False
        self.stuck: bool = False


# ---------------------------------------------------------------------------
# RoverAgent
# ---------------------------------------------------------------------------

class RoverAgent:
    """
    The Mars rover.

    State::

        S = (position, KB, visited, perception_state)

    Attributes:
        position: Current (x, y) coordinate.
        kb:       The rover's propositional knowledge base.
        visited:  Cells the rover has occupied.
        sensors:  Its sensor suite — the only route to the environment.
    """

    def __init__(self,
                 environment: MarsEnvironment,
                 kb: KnowledgeBase,
                 step_callback: Optional[Callable[[DecisionRecord], None]] = None,
                 verbose: bool = True):
        self.environment = environment
        self.kb = kb
        self.sensors = SensorSystem(environment)
        self.step_callback = step_callback
        self.verbose = verbose

        self.position: Tuple[int, int] = environment.start_pos
        self.visited: Set[Tuple[int, int]] = set()
        self.step_count: int = 0
        self.is_done: bool = False
        self.mission_success: bool = False

        self.metrics = Metrics()

        self._path_stack: List[Tuple[int, int]] = []   # for backtracking
        self._investigated: Set[Tuple[int, int]] = set()
        self._last_record: Optional[DecisionRecord] = None
        self._max_steps = (environment.width * environment.height
                           * MAX_STEPS_FACTOR)

        self._initialize_kb()

    # ------------------------------------------------------------------
    # Output helper
    # ------------------------------------------------------------------

    def _say(self, message: str = "", tag: str = "") -> None:
        if self.verbose:
            log(message, tag)

    # ------------------------------------------------------------------
    # Initial knowledge
    # ------------------------------------------------------------------

    def _initialize_kb(self) -> None:
        """
        Seed the KB with the only two things the rover knows a priori:
        where it is standing (and that the ground under it holds), and
        where it has been ordered to go.

        Everything else must be perceived.
        """
        sx, sy = self.position
        gx, gy = self.environment.goal_pos

        self._say("")
        self._say("=" * 60, "step")
        self._say("  KNOWLEDGE BASE INITIALIZATION", "step")
        self._say("=" * 60, "step")
        self._say(f"  Start position: ({sx},{sy})")
        self._say(f"  Goal position:  ({gx},{gy})")
        self._say("")
        self._say("  Initial axioms (the rover knows nothing else):")

        # The rover is standing on this cell, so it is safe by observation.
        self.kb.tell_cell_status(sx, sy, "SAFE")
        self.kb.tell_at(sx, sy)
        self.kb.tell(f"Visited_{sx}_{sy}", True)

        # Mission objective + Rule 5.
        self.kb.tell(f"Goal_{gx}_{gy}", True)
        self.kb.add_goal_rule(gx, gy)

        self.visited.add(self.position)
        self.metrics.cells_visited = 1

        self._say("")
        self._say(f"  KB initialized: {self.kb.fact_count} facts, "
                  f"{self.kb.rule_count} rules, "
                  f"{self.kb.clause_count} CNF clauses")
        self._say("=" * 60, "step")

    # ==================================================================
    # ONE AGENT CYCLE
    # ==================================================================

    def step(self) -> DecisionRecord:
        """
        Run one full PERCEIVE → TELL → INFER → ASK → DECIDE → ACT cycle.

        Returns:
            A :class:`DecisionRecord` describing the entire cycle.
        """
        self.step_count += 1
        x, y = self.position
        record = DecisionRecord(self.step_count, (x, y))

        self._say("")
        self._say("=" * 60, "step")
        self._say(f"  ROVER STEP {self.step_count:02d}", "step")
        self._say("=" * 60, "step")
        self._say(f"  CURRENT STATE:   At_{x}_{y}")
        self._say(f"  CURRENT POSITION: ({x},{y})   GOAL: "
                  f"{self.environment.goal_pos}")

        self._perceive_and_tell(record)
        self._infer(record)
        candidates = self._evaluate_candidates(record)
        acted = self._decide_and_act(record, candidates)

        if acted:
            self._check_goal(record)

        record.explanation = self._build_explanation(record)
        record.path_cost = self.metrics.path_cost
        self._sync_metrics()

        if self.step_count >= self._max_steps and not self.is_done:
            self._say("")
            self._say(f"  STEP BUDGET EXHAUSTED ({self._max_steps} steps) — "
                      f"terminating mission.", "result")
            self.is_done = True
            self.mission_success = False
            record.stuck = True
            self.metrics.stop_timer()

        self._say("")
        self._say(f"  Step {self.step_count} complete — KB now holds "
                  f"{self.kb.fact_count} facts / {self.kb.clause_count} clauses")
        self._say("=" * 60, "step")

        self._last_record = record
        if self.step_callback:
            self.step_callback(record)
        return record

    # ------------------------------------------------------------------
    # 1 + 2. PERCEIVE  →  TELL(KB)
    # ------------------------------------------------------------------

    def _perceive_and_tell(self, record: DecisionRecord) -> None:
        """Read the sensors and assert every perception into the KB."""
        x, y = self.position

        self._say("")
        self._say("  [1] PERCEIVE", "perceive")
        events = self.sensors.perceive_all(x, y)
        for event in events:
            self._say(f"      {event}", "perceive")
            record.perceptions.append(event.description)

        self._say("")
        self._say(f"  [2] TELL(KB) — asserting {len(events)} perceptions",
                  "tell")

        for event in events:
            self._tell_perception(event, record)

    def _tell_perception(self, event: PerceptionEvent,
                         record: DecisionRecord) -> None:
        """Convert one perception event into KB facts and rules."""
        cx, cy = event.cell

        if event.cell_type == CellType.HAZARD:
            self._say(f"\n  PERCEPTION EVENT: hazard signal at ({cx},{cy})",
                      "perceive")
        elif event.cell_type == CellType.RADIATION:
            self._say(f"\n  PERCEPTION EVENT: radiation signal at ({cx},{cy})",
                      "perceive")

        for symbol, positive in event.propositions:
            before = self.kb.fact_count
            self.kb.tell(symbol, positive)
            if self.kb.fact_count != before:
                prefix = "" if positive else "¬"
                record.kb_tells.append(f"TELL: {prefix}{symbol}")

        self.kb.install_rules_for(cx, cy, event.status)

        # Rule 4: At_x_y ∧ CanMove_x2_y2 → MoveTo_x2_y2, instantiated for
        # this neighbour of the rover's current cell.
        if event.cell != self.position:
            self.kb.add_move_rule(*self.position, cx, cy)

    # ------------------------------------------------------------------
    # 3. INFER — forward chaining
    # ------------------------------------------------------------------

    def _infer(self, record: DecisionRecord) -> None:
        """Derive every new fact that follows from the updated KB."""
        self._say("")
        self._say("  [3] INFER — forward chaining (Modus Ponens)", "infer")

        derived = self.kb.infer_forward()
        record.forward_inferences = derived

        if derived:
            self._say(f"  DERIVED {len(derived)} NEW FACT(S): "
                      f"{', '.join(derived)}", "infer")
        else:
            self._say("  No new facts derivable — KB already at fixed point.",
                      "infer")

    # ------------------------------------------------------------------
    # 4. ASK(KB) — evaluate every candidate action
    # ------------------------------------------------------------------

    def _evaluate_candidates(self, record: DecisionRecord) -> List[Dict]:
        """
        Query the KB about each neighbouring cell.

        A candidate is accepted **only** if ``KB ⊨ CanMove_x_y``.  Failing
        that, the rover distinguishes two very different situations:

          * the KB entails a danger fact  → the cell is *known* unsafe
          * the KB entails nothing either way → the cell is *unclassified*,
            and may be worth investigating (Rule 6)
        """
        x, y = self.position
        goal = self.environment.goal_pos
        candidates: List[Dict] = []

        self._say("")
        self._say("  [4] ASK(KB) — evaluating candidate actions", "ask")

        for direction, (dx, dy) in DIRECTIONS.items():
            nx, ny = x + dx, y + dy
            if not self.environment.is_in_bounds(nx, ny):
                continue

            remaining_x = abs(nx - goal[0])
            remaining_y = abs(ny - goal[1])

            info = {
                "direction": direction,
                "target": (nx, ny),
                "accepted": False,
                "investigate": False,
                "reason": "",
                "backward_explain": "",
                "ask_result": None,
                # Primary preference: Manhattan distance to the goal.
                "manhattan": remaining_x + remaining_y,
                # Tie-break: Chebyshev distance.  Among equally-close safe
                # cells, prefer the one that keeps progress on both axes
                # balanced — a corner-hugging route commits early to one
                # edge and strands the rover when that edge is blocked.
                "chebyshev": max(remaining_x, remaining_y),
                "visited": (nx, ny) in self.visited,
            }

            self._say("")
            self._say(f"  CANDIDATE: {direction} → ({nx},{ny})", "ask")

            # Backward reasoning: what would have to hold for this move?
            backward = self.kb.backward_explain(f"CanMove_{nx}_{ny}", True)
            for line in backward.split("\n"):
                self._say(f"    {line}", "ask")
            info["backward_explain"] = backward

            # The decisive query.
            answer = self.kb.ask_can_move(nx, ny)
            info["ask_result"] = answer

            if answer.entailed:
                info["accepted"] = True
                info["reason"] = f"KB ⊨ CanMove_{nx}_{ny} — logically safe"
                self._say(f"  DECISION INPUT: KB ⊨ CanMove_{nx}_{ny} "
                          f"→ ACTION PERMITTED", "result")
            else:
                self._classify_rejection(info, nx, ny)
                record.rejected_count += 1
                self.metrics.unsafe_actions_rejected += 1

            candidates.append(info)

        record.candidates_evaluated = candidates
        return candidates

    def _classify_rejection(self, info: Dict, nx: int, ny: int) -> None:
        """
        Explain *why* a candidate failed, using only what the KB entails.

        There is a real logical difference between "known dangerous" and
        "not known to be safe", and the rover responds differently to each.
        """
        hazard = self.kb.ask(f"Hazard_{nx}_{ny}", True,
                             use_model_checking=False, quiet=True)
        radiation = self.kb.ask(f"Radiation_{nx}_{ny}", True,
                                use_model_checking=False, quiet=True)
        unknown = self.kb.ask(f"Unknown_{nx}_{ny}", True,
                              use_model_checking=False, quiet=True)

        if hazard.entailed:
            self._say(f"  RULE ACTIVATED: Hazard_{nx}_{ny} → "
                      f"¬MoveForward_{nx}_{ny}   (Rule 1)", "result")
            self._say(f"  MODUS PONENS:   Hazard_{nx}_{ny} is entailed, "
                      f"therefore ¬MoveForward_{nx}_{ny}", "result")
            info["reason"] = (f"HAZARD entailed at ({nx},{ny}) → "
                              f"¬MoveForward (Rule 1)")

        elif radiation.entailed:
            self._say(f"  RULE ACTIVATED: Radiation_{nx}_{ny} → "
                      f"¬Enter_{nx}_{ny}   (Rule 2)", "result")
            self._say(f"  MODUS PONENS:   Radiation_{nx}_{ny} is entailed, "
                      f"therefore ¬Enter_{nx}_{ny}", "result")
            info["reason"] = (f"RADIATION entailed at ({nx},{ny}) → "
                              f"¬Enter (Rule 2)")

        elif unknown.entailed and (nx, ny) not in self._investigated:
            # Rule 6 fires: unclassified terrain is an *obligation to look*,
            # not merely an obstacle.
            self._say(f"  RULE ACTIVATED: Unknown_{nx}_{ny} → "
                      f"Investigate_{nx}_{ny}   (Rule 6)", "result")
            self._say(f"  KB ⊭ CanMove_{nx}_{ny}: terrain unclassified, so "
                      f"Rule 3's antecedent cannot be satisfied.", "result")
            info["investigate"] = True
            info["reason"] = (f"UNCLASSIFIED at ({nx},{ny}) — "
                              f"Rule 6 licenses INVESTIGATE")

        else:
            self._say(f"  KB ⊭ CanMove_{nx}_{ny} — no rule establishes "
                      f"traversability.", "result")
            info["reason"] = f"KB ⊭ CanMove_{nx}_{ny} — not provably safe"

        self._say(f"  DECISION INPUT: ACTION REJECTED — {info['reason']}",
                  "result")

    # ------------------------------------------------------------------
    # 5 + 6. DECIDE  →  ACT
    # ------------------------------------------------------------------

    def _decide_and_act(self, record: DecisionRecord,
                        candidates: List[Dict]) -> bool:
        """
        Choose an action and carry it out.

        Priority:
          1. Move to a logically safe, *unvisited* cell (forward progress).
          2. Investigate unclassified terrain that is at least as promising
             as the best safe move (Rule 6) — information is cheap.
          3. Backtrack along the path already travelled.
          4. Declare the mission blocked.

        Note there is no "revisit a safe cell voluntarily" tier: moving
        into an already-visited cell can only ever be useful as a step
        back toward an unexplored branch, and that is exactly what
        backtracking already does via the path stack. Without this
        restriction the rover can shuttle forever between two safe
        visited cells whenever they happen to be mutually closest to the
        goal, never making progress and never recognising it is stuck.

        Returns True if an action was taken.
        """
        self._say("")
        self._say("  [5] DECIDE", "decision")

        safe = [c for c in candidates if c["accepted"]]
        investigable = [c for c in candidates if c["investigate"]]

        pool = [c for c in safe if not c["visited"]]
        rank = lambda c: (c["manhattan"], c["chebyshev"])
        best_safe = min(pool, key=rank) if pool else None

        # Should the rover spend a sweep on unclassified terrain?
        # Worth it when the unknown cell is at least as close to the goal as
        # the best confirmed-safe option — it may open a shorter route, and
        # if it turns out dangerous the rover has learned that for free.
        best_unknown = min(investigable, key=rank) if investigable else None

        should_investigate = (
            best_unknown is not None
            and (best_safe is None
                 or best_unknown["manhattan"] <= best_safe["manhattan"]))

        if should_investigate:
            return self._act_investigate(record, best_unknown)

        if best_safe is not None:
            return self._act_move(record, best_safe)

        return self._act_backtrack(record)

    def _act_move(self, record: DecisionRecord, choice: Dict) -> bool:
        """Execute a MOVE action and update the successor state."""
        direction = choice["direction"]
        target = choice["target"]

        self._say(f"  DECISION: MOVE {direction} → ({target[0]},{target[1]})",
                  "decision")
        self._say(f"  JUSTIFICATION: KB ⊨ CanMove_{target[0]}_{target[1]} "
                  f"— logically safe. Chosen among the safe options by "
                  f"Manhattan distance {choice['manhattan']} "
                  f"(tie-break: Chebyshev {choice['chebyshev']}).",
                  "decision")

        record.action_type = "MOVE"
        record.chosen_action = direction
        record.chosen_target = target

        self._apply_move(record, target, direction)
        return True

    def _act_investigate(self, record: DecisionRecord, choice: Dict) -> bool:
        """
        Execute an INVESTIGATE action.

        The rover stays put, spends a close-range sensor sweep on the target
        cell, and TELLs the KB what it finds.  ``Unknown_x_y`` is retracted
        and replaced by a real classification, after which Rules 1–3 decide
        whether the cell may be entered.
        """
        target = choice["target"]
        tx, ty = target

        self._say(f"  DECISION: INVESTIGATE ({tx},{ty})", "decision")
        self._say(f"  JUSTIFICATION: Unknown_{tx}_{ty} → Investigate_{tx}_{ty} "
                  f"(Rule 6); the cell is at least as close to the goal as "
                  f"any confirmed-safe option, so classifying it is worth "
                  f"one sensor sweep.", "decision")

        record.action_type = "INVESTIGATE"
        record.chosen_action = f"INVESTIGATE {choice['direction']}"
        record.chosen_target = target

        self._say("")
        self._say("  [6] ACT — close-range sensor sweep", "perceive")
        event = self.sensors.investigate(tx, ty)
        self._say(f"      {event}", "perceive")
        record.perceptions.append(event.description)

        self._say("")
        self._say(f"  TELL(KB) — Unknown_{tx}_{ty} resolved to "
                  f"{event.cell_type.value}", "tell")

        # Unknown_x_y is a fluent of the rover's *knowledge*: true only
        # while the cell is unclassified.  Retract it explicitly.
        self.kb.retract(f"Unknown_{tx}_{ty}", True,
                        reason="cell classified by investigation")
        for symbol, positive in event.propositions:
            self.kb.tell(symbol, positive)
        self.kb.install_rules_for(tx, ty, event.status)

        self._investigated.add(target)
        self.metrics.investigations += 1
        self.metrics.path_cost += INVESTIGATE_COST

        self._say("")
        self._say("  INFER — consequences of the new classification", "infer")
        derived = self.kb.infer_forward()
        record.forward_inferences.extend(derived)
        if derived:
            self._say(f"  DERIVED: {', '.join(derived)}", "infer")

        # Report the outcome the way the examiner needs to see it.
        verdict = self.kb.ask_can_move(tx, ty, quiet=True)
        if verdict.entailed:
            self._say(f"  OUTCOME: KB ⊨ CanMove_{tx}_{ty} — the cell is now "
                      f"a legal move.", "result")
        else:
            self._say(f"  OUTCOME: KB ⊭ CanMove_{tx}_{ty} — investigation "
                      f"revealed danger; this route is now closed.", "result")

        self._say("")
        self._say(f"  SUCCESSOR STATE: At_{self.position[0]}_"
                  f"{self.position[1]} (unchanged — investigation does not "
                  f"move the rover)")
        self._say(f"  PATH COST: {self.metrics.path_cost:.1f} "
                  f"(+{INVESTIGATE_COST} for the sweep)")

        record.successor_state = self.position
        return True

    def _act_backtrack(self, record: DecisionRecord) -> bool:
        """
        No safe forward move and nothing left to investigate — retreat along
        the path already travelled.

        The path stack is *popped*, so the rover genuinely unwinds its route
        instead of oscillating between two cells.
        """
        self._say("  DECISION: no candidate satisfies KB ⊨ CanMove — "
                  "attempting to backtrack", "decision")

        while self._path_stack:
            previous = self._path_stack.pop()
            if previous == self.position:
                continue

            self._say(f"  BACKTRACK: returning to ({previous[0]},"
                      f"{previous[1]}) — already traversed, so "
                      f"KB ⊨ CanMove_{previous[0]}_{previous[1]} holds.",
                      "decision")

            record.action_type = "BACKTRACK"
            record.chosen_action = "BACKTRACK"
            record.chosen_target = previous

            self._apply_move(record, previous, "BACKTRACK",
                             push_history=False)
            return True

        self._say("  MISSION BLOCKED: no safe action and no route back.",
                  "result")
        self.is_done = True
        self.mission_success = False
        record.stuck = True
        self.metrics.stop_timer()
        return False

    def _apply_move(self, record: DecisionRecord,
                    target: Tuple[int, int],
                    direction: str,
                    push_history: bool = True) -> None:
        """Perform the state transition and update the position fluent."""
        origin = self.position

        self._say("")
        self._say("  [6] ACT + SUCCESSOR STATE", "decision")
        self._say(f"  CURRENT STATE:   At_{origin[0]}_{origin[1]}")
        self._say(f"  ACTION:          {direction}")
        self._say(f"  SUCCESSOR STATE: At_{target[0]}_{target[1]}")

        if push_history:
            self._path_stack.append(origin)

        self.position = target
        tx, ty = target

        self._say("")
        self._say("  KB UPDATE (fluents):", "tell")
        # At_x_y is a fluent — the previous position must be retracted or
        # the KB would assert the rover is in two places at once.
        self.kb.tell_at(tx, ty, previous=origin)
        self.kb.tell(f"Visited_{tx}_{ty}", True)

        self.metrics.moves += 1
        self.metrics.path_cost += MOVE_COST

        if target not in self.visited:
            self.visited.add(target)
            self.metrics.cells_visited += 1

        record.successor_state = target
        self._say(f"  PATH COST: {self.metrics.path_cost:.1f}")

    # ------------------------------------------------------------------
    # 7. Goal test
    # ------------------------------------------------------------------

    def _check_goal(self, record: DecisionRecord) -> None:
        """
        Goal test — carried out *logically*.

        The rover does not compare coordinates to decide it has finished.
        It TELLs the KB where it now is and asks whether MissionComplete is
        entailed; Rule 5 (At_goal → MissionComplete) does the rest through
        forward chaining.  This keeps the termination condition inside the
        knowledge base like every other decision.
        """
        derived = self.kb.infer_forward(quiet=True)
        if derived:
            record.forward_inferences.extend(derived)

        if not self.kb.ask_mission_complete():
            return

        gx, gy = self.position
        self.is_done = True
        self.mission_success = True
        record.mission_complete = True

        self._say("")
        self._say("  [7] GOAL TEST", "result")
        self._say(f"  RULE 5 ACTIVATED: At_{gx}_{gy} → MissionComplete",
                  "result")
        self._say(f"  MODUS PONENS:     At_{gx}_{gy} is a fact, therefore "
                  f"MissionComplete is derived.", "result")
        self._say(f"  ASK: KB ⊨ MissionComplete ?   RESULT: ENTAILED",
                  "result")
        self._say("")
        self._say(f"  ★ GOAL REACHED at ({gx},{gy}) — MISSION COMPLETE",
                  "result")

        self.metrics.stop_timer()
        self.metrics.mission_success = True
        self._sync_metrics()
        log(self.metrics.format_final_report())

    # ------------------------------------------------------------------
    # Explanation panel
    # ------------------------------------------------------------------

    def _build_explanation(self, record: DecisionRecord) -> str:
        """Build the "why did the rover act?" narrative for the UI."""
        lines = [f"WHY DID THE ROVER ACT THIS WAY?   (Step {record.step})",
                 f"  Current Position: {record.position}",
                 f"  Goal:             {self.environment.goal_pos}",
                 ""]

        for candidate in record.candidates_evaluated:
            direction = candidate["direction"]
            target = candidate["target"]
            if candidate["accepted"]:
                marker, verdict = "✓", "ACCEPTED"
            elif candidate["investigate"]:
                marker, verdict = "?", "UNCLASSIFIED"
            else:
                marker, verdict = "✗", "REJECTED"

            lines.append(f"  {marker} {direction} → {target}: {verdict}")
            lines.append(f"      {candidate['reason']}")

            # The decisive line of the backward-reasoning trace.
            backward = candidate.get("backward_explain", "")
            for line in backward.split("\n"):
                if "→" in line and ("CONCLUDE" in line):
                    lines.append(f"      {line.strip()}")
                    break

        lines.append("")
        if record.action_type == "INVESTIGATE":
            lines.append(f"  ► ACTION: INVESTIGATE {record.chosen_target}")
            lines.append(f"    Rule 6: Unknown → Investigate. The rover pays "
                         f"{INVESTIGATE_COST} to classify the cell rather "
                         f"than assume it is safe.")
        elif record.action_type == "MOVE":
            tx, ty = record.chosen_target
            lines.append(f"  ► ACTION: MOVE {record.chosen_action} → "
                         f"{record.chosen_target}")
            lines.append(f"    Licensed by: KB ⊨ CanMove_{tx}_{ty}")
            lines.append(f"    Successor state: At_{tx}_{ty}")
        elif record.action_type == "BACKTRACK":
            lines.append(f"  ► ACTION: BACKTRACK → {record.chosen_target}")
            lines.append("    Every forward candidate was rejected by the KB; "
                         "the rover retreats along known-safe ground.")
        else:
            lines.append("  ► ACTION: none — no logically permitted action "
                         "remains.")

        lines.append(f"  Path Cost: {self.metrics.path_cost:.1f}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Metrics + reset
    # ------------------------------------------------------------------

    def _sync_metrics(self) -> None:
        """Copy the KB's counters into the metrics record."""
        self.metrics.total_steps = self.step_count
        self.metrics.inference_ops = self.kb.inference_count
        self.metrics.resolution_ops = self.kb.resolution_count
        self.metrics.model_check_ops = self.kb.model_check_count
        self.metrics.models_enumerated = self.kb.models_enumerated
        self.metrics.kb_facts_final = self.kb.fact_count
        self.metrics.kb_clauses_final = self.kb.clause_count
        self.metrics.kb_rules_final = self.kb.rule_count
        self.metrics.tell_ops = self.kb.tell_count
        self.metrics.ask_ops = self.kb.ask_count
        self.metrics.perceptions = self.sensors.perception_count

    def reset(self) -> None:
        """Return the rover, its KB and its sensors to the initial state."""
        self.position = self.environment.start_pos
        self.visited = set()
        self.step_count = 0
        self.is_done = False
        self.mission_success = False
        self.metrics = Metrics()
        self._path_stack = []
        self._investigated = set()
        self._last_record = None

        self.environment.reset_revelations()
        self.sensors.reset()
        self.kb.reset()
        self._initialize_kb()

    @property
    def last_record(self) -> Optional[DecisionRecord]:
        return self._last_record
