# TECHNICAL SUMMARY — AI Hackathon Submission
## Autonomous Mars Rover — Propositional Logic Knowledge-Based Agent

---

**Course Code:** [COURSE CODE]

**Group ID:** [GROUP ID]

**Team Members:**
- [MEMBER 1]
- [MEMBER 2]
- [MEMBER 3]

**Selected Track:** Unit 3 — Logical Agents / Propositional Logic

**GitHub URL:** [GITHUB URL]

---

## Project Overview

An autonomous Mars rover agent that navigates a 7×7 grid using a real Propositional Logic Knowledge Base. Every movement decision is derived from logical inference — not hard-coded pathfinding.

---

## PEAS Framework

| Component | Details |
|---|---|
| **Performance** | Reach goal safely, avoid hazards/radiation, minimize path cost, correct inference |
| **Environment** | 7×7 Mars grid: safe terrain, hazard zones, radiation zones, unknown cells, goal |
| **Actuators** | Move UP / DOWN / LEFT / RIGHT, Investigate unknown cell |
| **Sensors** | Hazard sensor, Radiation sensor, Terrain sensor, Goal sensor, Adjacent-cell perception |

---

## Core Algorithmic Formulation

### Agent Cycle (per step):
```
PERCEIVE (sensors read 4 adjacent cells)
  → TELL(KB): Assert all perception propositions
  → INFER: Forward chaining derives new facts (Modus Ponens)
  → For each candidate action:
       ASK(KB): KB ⊨ CanMove_{x}_{y} ?
       RESOLUTION: Refutation proof (add ¬query, derive {} )
  → DECIDE: Accepted candidates sorted by Manhattan distance to goal
  → ACT: Move to chosen cell
  → UPDATE KB: At_x_y, Visited_x_y (Successor State)
```

### Inference Methods:
1. **Resolution Refutation** (primary): Add ¬α, derive empty clause
2. **Forward Chaining** (supplementary): Fire rules when antecedents known
3. **Model Checking** (verification): Truth-table enumeration for local symbols
4. **Backward Reasoning** (explanation): Goal → Required conditions check

---

## Logic Rules

| Rule | Form | Purpose |
|---|---|---|
| 1 | `Hazard_x_y → ¬MoveForward_x_y` | Hazard blocks movement |
| 2 | `Radiation_x_y → ¬Enter_x_y` | Radiation blocks entry |
| 3 | `Safe∧¬Hazard∧¬Radiation → CanMove` | Safe terrain allows movement |
| 4 | `At_x_y ∧ CanMove_x2_y2 → MoveTo_x2_y2` | Position enables action |
| 5 | `At_goal → MissionComplete` | Goal recognition |
| 6 | `Unknown_x_y → Investigate_x_y` | Unknown requires investigation |
| 7 | `PerceiveHazard → Hazard` | Sensor → proposition |
| 8 | `PerceiveRadiation → Radiation` | Sensor → proposition |

### CNF Conversion Pipeline:
```
Biconditional elim → Implication elim → De Morgan's → Double negation → Distribution
```

### Example:
```
Hazard_2_3 → ¬MoveForward_2_3
  → ¬Hazard_2_3 ∨ ¬MoveForward_2_3   (CNF clause)
```

---

## Complexity Analysis

| Method | Complexity | Notes |
|---|---|---|
| Model Checking | O(2^n) | Limited to ≤14 local symbols |
| Resolution | Exponential (worst case) | Practical: fast for small prop. sets |
| Forward Chaining | O(rules × facts) | Linear in rule/fact count |

---

## Observed Metrics (Default 7×7 Map)

| Metric | Typical Value |
|---|---|
| Execution Time | < 1.0 sec |
| Moves | ~14–20 |
| Path Cost | ~14–20 |
| Cells Visited | ~10–15 |
| Inference Operations | ~30–50 |
| Resolution Operations | ~50–100 |
| Unsafe Actions Rejected | ~5–15 per run |

---

## Key Files

| File | Role |
|---|---|
| `main.py` | Entry point |
| `knowledge_base.py` | TELL / ASK / INFER API |
| `logic.py` | Literal, Clause, CNFConverter |
| `resolution.py` | Resolution engine |
| `rover.py` | KB agent decision loop |
| `environment.py` | Mars grid (separate from KB) |
| `ui.py` | Tkinter visual interface |

---

## How to Run

```bash
python main.py                 # Full UI
python main.py --no-ui         # Console only
set PYTHONIOENCODING=utf-8
python tests/test_logic.py     # Run logic tests
python tests/test_rover.py     # Run rover tests
```

---

*[Fill in team details before submission]*
