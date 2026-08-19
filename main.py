"""
main.py
=======
Entry point for the Autonomous Mars Rover — Propositional Logic
Knowledge-Based Agent.

"""

from __future__ import annotations

import argparse
import sys

# Imported first: configures stdout for UTF-8, line-buffered output so the
# logical notation prints correctly and appears live rather than in bursts.
import console
from console import log

from environment import MarsEnvironment
from knowledge_base import KnowledgeBase
from resolution import ResolutionEngine
from rover import RoverAgent
from simulation import Simulation


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous Mars Rover -- Propositional Logic "
                    "Knowledge-Based Agent (Unit 3: Logical Agents)")
    parser.add_argument("--random", action="store_true",
                        help="use a randomly generated map instead of the "
                             "deterministic demonstration map")
    parser.add_argument("--seed", type=int, default=42,
                        help="random seed for map generation (default: 42)")
    parser.add_argument("--no-ui", action="store_true",
                        help="run headless: console output only")
    parser.add_argument("--delay", type=int, default=800,
                        help="auto-run delay between steps in ms "
                             "(default: 800)")
    parser.add_argument("--demo-rules", action="store_true",
                        help="print Modus Ponens / Modus Tollens / "
                             "disjunctive syllogism as resolution steps, "
                             "then exit")
    return parser.parse_args(argv)


def print_header() -> None:
    """Print the startup banner."""
    log("=" * 60)
    log("       AUTONOMOUS MARS ROVER")
    log("       Propositional Logic Knowledge-Based Agent")
    log("       Unit 3: Logical Agents")
    log("=" * 60)
    log("  Agent cycle: PERCEIVE → TELL(KB) → INFER → ASK(KB) →")
    log("               DECIDE → ACT → SUCCESSOR STATE → repeat")
    log("=" * 60)


def print_rule_schemas(kb: KnowledgeBase) -> None:
    """List the eight domain rule schemas the KB instantiates per cell."""
    log("")
    log("  PROPOSITIONAL RULE SCHEMAS LOADED")
    log("  " + "-" * 56)
    for name, rule, meaning in kb.get_rule_schemas():
        log(f"    {name}: {rule}")
        log(f"            {meaning}")
    log("  " + "-" * 56)
    log("  Propositional logic has no variables, so the KB instantiates a")
    log("  concrete ground rule for each cell the rover actually perceives.")


def run_headless(sim: Simulation) -> int:
    """
    Run the mission without a UI.

    Returns:
        Process exit code: 0 on mission success, 1 otherwise.
    """
    log("")
    log("=" * 60)
    log("  HEADLESS MODE — console-only simulation")
    log("=" * 60)

    sim.run_to_completion()

    log("")
    if sim.rover.mission_success:
        log("  RESULT: MISSION SUCCESSFUL")
        return 0

    log("  RESULT: MISSION FAILED — the rover could not reach the goal "
        "through terrain it was able to prove safe.")
    return 1


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.demo_rules:
        print_header()
        log("")
        log(ResolutionEngine().demonstrate_all())
        return 0

    print_header()

    # 1. Environment — ground truth, never read by the rover directly.
    env = MarsEnvironment(use_random=args.random, seed=args.seed)
    log("")
    log(env.get_map_description())
    env.print_grid()

    # 2. Knowledge base — empty; the rover must learn everything.
    kb = KnowledgeBase()
    print_rule_schemas(kb)

    # 3. The agent.
    rover = RoverAgent(environment=env, kb=kb)

    # 4. The controller.
    sim = Simulation(environment=env, kb=kb, rover=rover,
                     step_delay_ms=args.delay)

    # 5. Run.
    if args.no_ui:
        return run_headless(sim)

    try:
        from ui import MarsRoverUI
    except Exception as error:                      # pragma: no cover
        log(f"\n  UI unavailable ({error.__class__.__name__}: {error}).")
        log("  Falling back to headless mode.\n")
        return run_headless(sim)

    app = MarsRoverUI(simulation=sim)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
