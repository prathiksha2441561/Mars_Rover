"""
knowledge_base.py
=================
The rover's Propositional Logic Knowledge Base — the heart of the
Knowledge-Based Agent.

Public API (the vocabulary from Unit 3)
---------------------------------------
    TELL(KB, α)      add a sentence to the knowledge base
    ASK(KB, α)       ask whether KB ⊨ α
    RETRACT(KB, α)   remove a sentence
    INFER()          forward chaining: derive new facts from rules
    GET_FACTS()      the atomic sentences currently believed
    GET_RULES()      the implications currently believed
    GET_CLAUSES()    the CNF clause set used by resolution

How a query is answered
-----------------------
``ASK`` runs **two independent inference procedures** and reports both:

    1. RESOLUTION      — syntactic: proof by refutation (KB ∧ ¬α ⊢ {})
    2. MODEL CHECKING  — semantic: enumerate models of the KB and check
                         that α holds in all of them

They answer the same question by completely different means, so their
agreement is an observable demonstration of soundness and completeness.
The rover always *acts* on the resolution result; model checking is the
cross-check.

Internal representation
-----------------------
    _facts    set of Literal      — atomic sentences (positive or negative)
    _rules    list of Rule        — implications, stored once each
    _clauses  cached CNF set      — rebuilt only when the KB changes
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set, Tuple

import console
from console import log
from logic import (Clause, Literal, classify_clauses,
                   make_conjunction_implication_clauses)
from model_checker import ModelChecker
from resolution import ResolutionEngine


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

class Rule:
    """
    A propositional rule:  A₁ ∧ A₂ ∧ … ∧ Aₙ → C

    Stored symbolically so it can be displayed in the UI and explained in
    backward reasoning, and converted to CNF on demand for resolution.

    Every rule in this project is a **definite clause** (exactly one
    positive literal after CNF conversion), which is why forward chaining
    with Modus Ponens is sufficient to derive the rover's conclusions.
    """

    def __init__(self,
                 antecedents: List[Tuple[str, bool]],
                 consequent_symbol: str,
                 consequent_positive: bool,
                 name: str = ""):
        self.antecedents = list(antecedents)
        self.consequent_symbol = consequent_symbol
        self.consequent_positive = consequent_positive
        self.name = name

    # -- identity -------------------------------------------------------

    def signature(self) -> Tuple:
        """
        A hashable identity for the rule.

        Used to guarantee each logical rule is stored exactly once, no
        matter how many times the rover re-perceives the same cell.
        """
        return (tuple(sorted(self.antecedents)),
                self.consequent_symbol,
                self.consequent_positive)

    def __eq__(self, other) -> bool:
        return isinstance(other, Rule) and self.signature() == other.signature()

    def __hash__(self) -> int:
        return hash(self.signature())

    # -- conversion -----------------------------------------------------

    def to_clauses(self) -> List[Clause]:
        """
        Convert the rule to CNF.

            A ∧ B → C   ≡   ¬A ∨ ¬B ∨ C
        """
        return make_conjunction_implication_clauses(
            self.antecedents, self.consequent_symbol, self.consequent_positive)

    def to_model_check_tuple(self):
        """Export the rule in the form expected by :class:`ModelChecker`."""
        return (tuple(self.antecedents),
                self.consequent_symbol,
                self.consequent_positive)

    def symbols(self) -> Set[str]:
        """Every proposition symbol mentioned by the rule."""
        return {s for s, _ in self.antecedents} | {self.consequent_symbol}

    def __str__(self) -> str:
        antecedent = " ∧ ".join(
            (s if p else f"¬{s}") for s, p in self.antecedents)
        consequent = (self.consequent_symbol if self.consequent_positive
                      else f"¬{self.consequent_symbol}")
        return f"{antecedent} → {consequent}"

    def __repr__(self) -> str:
        return f"Rule({self})"


# ---------------------------------------------------------------------------
# The eight core rule schemas (documentation + UI display)
# ---------------------------------------------------------------------------

# These are the *schemas* — the general rules of the domain.  Because
# propositional logic has no variables, the KB instantiates a concrete
# ground rule for each cell the rover actually perceives (see
# ``tell_cell_status``).  Listing the schemas here keeps the connection
# between the class notes and the running code explicit.
RULE_SCHEMAS: List[Tuple[str, str, str]] = [
    ("Rule 1", "Hazard_x_y → ¬MoveForward_x_y",
     "A detected hazard forbids moving into that cell."),
    ("Rule 2", "Radiation_x_y → ¬Enter_x_y",
     "A radiation zone must not be entered."),
    ("Rule 3", "Safe_x_y ∧ ¬Hazard_x_y ∧ ¬Radiation_x_y → CanMove_x_y",
     "Terrain confirmed safe and clear of both dangers is traversable."),
    ("Rule 4", "At_x_y ∧ CanMove_x2_y2 → MoveTo_x2_y2",
     "From the current cell, a traversable neighbour is a legal move."),
    ("Rule 5", "At_goal → MissionComplete",
     "Arriving at the goal completes the mission."),
    ("Rule 6", "Unknown_x_y → Investigate_x_y",
     "Unclassified terrain must be investigated, never assumed safe."),
    ("Rule 7", "PerceiveHazard_x_y → Hazard_x_y",
     "A hazard sensor reading establishes a hazard fact."),
    ("Rule 8", "PerceiveRadiation_x_y → Radiation_x_y",
     "A radiation sensor reading establishes a radiation fact."),
]


# ---------------------------------------------------------------------------
# KB log entry (for the UI panel)
# ---------------------------------------------------------------------------

class KBLogEntry:
    """One logged KB operation, displayed in the Knowledge Base panel."""

    def __init__(self, operation: str, content: str, detail: str = ""):
        self.operation = operation      # TELL | ASK | RESULT | INFER | RETRACT
        self.content = content
        self.detail = detail

    def __str__(self) -> str:
        if self.detail:
            return f"{self.operation}: {self.content}\n  → {self.detail}"
        return f"{self.operation}: {self.content}"


# ---------------------------------------------------------------------------
# ASK result
# ---------------------------------------------------------------------------

class AskResult:
    """
    The complete outcome of one ``ASK(KB, α)`` query.

    Carries both inference results so the UI and the console can show the
    full reasoning chain rather than a bare True/False.
    """

    def __init__(self, query: str):
        self.query = query
        self.entailed: bool = False
        self.method: str = ""            # how the answer was reached
        self.resolution_entailed: Optional[bool] = None
        self.resolution_ops: int = 0
        self.resolution_steps: List[str] = []
        self.model_check: Optional[dict] = None
        self.consistent: Optional[bool] = None   # do both methods agree?
        self.explanation: str = ""

    def __bool__(self) -> bool:
        return self.entailed

    def __iter__(self):
        # Allows `entailed, explanation = kb.ask(...)` alongside the
        # richer attribute-based access used elsewhere.
        return iter((self.entailed, self.explanation))


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """
    Propositional Logic Knowledge Base for the Mars rover.

    The rover owns exactly one of these.  It contains *only* what the
    rover has been told by its sensors — never the environment's ground
    truth.
    """

    def __init__(self, verbose: bool = True):
        """
        Args:
            verbose: When False the KB stops printing to the console.
                     Used by the test suite to keep output readable.
        """
        self.verbose = verbose

        self._facts: Set[Literal] = set()
        self._rules: List[Rule] = []
        self._rule_signatures: Set[Tuple] = set()   # de-duplication index
        self._log: List[KBLogEntry] = []

        self._resolution_engine = ResolutionEngine()
        self._model_checker = ModelChecker()

        self._inference_count = 0
        self._resolution_count = 0
        self._model_check_count = 0
        self._tell_count = 0
        self._ask_count = 0

        # Cached CNF clause set; invalidated whenever the KB changes.
        self._clause_cache: Optional[List[Clause]] = None

        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Output helper
    # ------------------------------------------------------------------

    def _say(self, message: str, tag: str = "") -> None:
        """Print to the live log unless the KB is in quiet mode."""
        if self.verbose:
            log(message, tag)

    def set_on_change(self, callback: Callable) -> None:
        """Register a callback fired whenever the KB changes."""
        self._on_change = callback

    def _notify_change(self) -> None:
        self._clause_cache = None          # KB changed → rebuild clauses
        if self._on_change:
            self._on_change()

    # ==================================================================
    # TELL
    # ==================================================================

    def tell(self, symbol: str, positive: bool = True) -> None:
        """
        TELL(KB, α) — assert an atomic sentence.

            kb.tell("Safe_2_3")          asserts   Safe_2_3
            kb.tell("Hazard_2_4", False) asserts  ¬Hazard_2_4

        If the complement is currently believed it is retracted first, so
        the KB never holds an outright contradiction.  (An inconsistent KB
        would entail *everything* — including that a hazard is safe.)
        """
        literal = Literal(symbol, positive)

        if literal in self._facts:
            return  # already known — nothing changes

        self._tell_count += 1
        complement = literal.negate()
        if complement in self._facts:
            self._facts.discard(complement)
            self._say(f"  RETRACT: {complement}  (superseded by new perception)",
                      "retract")
            self._log.append(KBLogEntry("RETRACT", str(complement),
                                        "consistency maintenance"))

        self._facts.add(literal)
        self._say(f"  TELL: {literal}", "tell")
        self._log.append(KBLogEntry("TELL", str(literal)))
        self._notify_change()

    def tell_rule(self, rule: Rule, announce: bool = True) -> bool:
        """
        TELL(KB, rule) — assert an implication.

        Returns True if the rule was new.  Re-asserting an identical rule
        is a no-op, which keeps the clause set from growing every time the
        rover re-perceives a cell it has already seen.
        """
        signature = rule.signature()
        if signature in self._rule_signatures:
            return False

        self._rule_signatures.add(signature)
        self._rules.append(rule)
        if announce:
            self._say(f"  RULE ADDED: {rule}", "rule")
            self._log.append(KBLogEntry("TELL", str(rule), "rule"))
        self._notify_change()
        return True

    # ==================================================================
    # ASK
    # ==================================================================

    def ask(self,
            symbol: str,
            positive: bool = True,
            use_model_checking: bool = True,
            quiet: bool = False) -> AskResult:
        """
        ASK(KB, α) — does the knowledge base entail α?

        Runs resolution (syntactic) and, when the local symbol set is
        small enough, model checking (semantic) as an independent check.

        Args:
            symbol:             Proposition symbol to query.
            positive:           False queries ¬symbol.
            use_model_checking: Run the semantic cross-check as well.
            quiet:              Suppress console output (used for the many
                                bookkeeping queries that would otherwise
                                drown out the interesting reasoning).

        Returns:
            An :class:`AskResult`; it is truthy exactly when KB ⊨ α.
        """
        self._ask_count += 1
        self._inference_count += 1

        query_literal = Literal(symbol, positive)
        result = AskResult(str(query_literal))

        verbose = self.verbose and not quiet
        if verbose:
            log("")
            log(f"  ASK: KB ⊨ {query_literal} ?", "ask")

        # Every query goes through the inference engine — including ones
        # whose answer is already an atomic fact.  Short-circuiting those
        # would be faster, but the point of the exercise is that the
        # rover's answers are *derived*, so the resolution proof is always
        # produced and always shown.
        if verbose and query_literal in self._facts:
            log(f"  NOTE: {query_literal} is already an atomic fact; "
                f"resolution should refute ¬{query_literal} in one step.",
                "ask")

        # -- Resolution (proof by refutation) ---------------------------
        clauses = self.get_clauses()
        resolution = self._resolution_engine.resolve(clauses, query_literal)
        self._resolution_count += resolution.resolution_ops

        result.resolution_entailed = resolution.entailed
        result.resolution_ops = resolution.resolution_ops
        result.resolution_steps = resolution.steps
        result.entailed = resolution.entailed
        result.method = "resolution"

        if verbose:
            label = "ENTAILED" if resolution.entailed else "NOT ENTAILED"
            log(f"  RESOLUTION RESULT: {label}  "
                f"({resolution.resolution_ops} resolution ops, "
                f"{len(clauses)} clauses)", "result")
            for step in resolution.key_steps():
                log(f"    {step}", "result")

        # -- Model checking (semantic cross-check) ----------------------
        if use_model_checking:
            model_check = self._run_model_check(symbol, positive)
            if model_check is not None:
                result.model_check = model_check
                result.consistent = (model_check["entailed"]
                                     == resolution.entailed)
                if verbose:
                    mc_label = ("ENTAILED" if model_check["entailed"]
                                else "NOT ENTAILED")
                    log(f"  MODEL CHECKING RESULT: {mc_label}  "
                        f"({model_check['models_checked']} models checked, "
                        f"{model_check['models_satisfying_kb']} satisfy KB)",
                        "result")
                    log(f"  CONSISTENT RESULT: "
                        f"{'YES' if result.consistent else 'NO — DISCREPANCY'}",
                        "result")

        result.explanation = self._format_ask_explanation(result, resolution)

        self._log.append(KBLogEntry(
            "ASK", f"KB ⊨ {query_literal} ?",
            "ENTAILED" if result.entailed else "NOT ENTAILED"))
        return result

    def _run_model_check(self, symbol: str, positive: bool) -> Optional[dict]:
        """
        Run the semantic cross-check over the *local* symbol set relevant
        to this query.  Returns None if even the local set is too large.
        """
        local_symbols = self._get_local_symbols(symbol)
        if len(local_symbols) > self._model_checker.max_symbols:
            return None

        relevant_rules = [
            rule.to_model_check_tuple()
            for rule in self._rules
            if rule.symbols() & local_symbols
        ]
        positive_facts = {lit.symbol for lit in self._facts if lit.positive}
        negative_facts = {lit.symbol for lit in self._facts if not lit.positive}

        self._model_check_count += 1
        return self._model_checker.check(
            facts=positive_facts,
            negated_facts=negative_facts,
            rules=relevant_rules,
            query_symbol=symbol,
            query_positive=positive,
            symbols=local_symbols)

    def _get_local_symbols(self, query_symbol: str) -> Set[str]:
        """
        Collect the small set of symbols *logically relevant* to the query.

        Model checking costs O(2^n), and by mid-mission the KB holds well
        over a hundred symbols — enumerating them all is hopeless.  So the
        symbol set is built in priority order:

        1. **Backward closure.**  Every rule that *concludes* the query
           symbol, then every rule concluding one of that rule's
           antecedents, and so on.  These are the rules a derivation of the
           query would actually have to use, so this is the neighbourhood
           that decides the answer.

        2. **Forward links, budget permitting.**  Rules where the query
           appears as an *antecedent* can still matter — ``Q → R`` together
           with ``¬R`` entails ``¬Q`` by Modus Tollens — so they are added
           afterwards while symbols remain within budget.

        Whatever does not fit is left out, and the model checker reports
        the restriction rather than hiding it.
        """
        budget = self._model_checker.max_symbols
        symbols: Set[str] = {query_symbol}

        # 1. Backward closure over rule consequents.
        frontier = {query_symbol}
        while frontier:
            next_frontier: Set[str] = set()
            for rule in self._rules:
                if rule.consequent_symbol not in frontier:
                    continue
                for symbol, _positive in rule.antecedents:
                    if symbol not in symbols:
                        if len(symbols) >= budget:
                            return symbols
                        symbols.add(symbol)
                        next_frontier.add(symbol)
            frontier = next_frontier

        # 2. Forward links (Modus Tollens routes), while budget remains.
        for rule in self._rules:
            if len(symbols) >= budget:
                break
            if any(symbol in symbols for symbol, _ in rule.antecedents):
                candidate = symbols | {rule.consequent_symbol}
                if len(candidate) <= budget:
                    symbols = candidate

        return symbols

    def _format_ask_explanation(self, result: AskResult,
                                resolution) -> str:
        """Build the multi-line explanation shown in the UI."""
        lines = [f"QUERY: KB ⊨ {result.query} ?"]
        lines.append(
            f"RESOLUTION RESULT: "
            f"{'ENTAILED' if result.resolution_entailed else 'NOT ENTAILED'}"
            f"  ({result.resolution_ops} ops)")

        if result.model_check:
            mc = result.model_check
            lines.append(
                f"MODEL CHECKING RESULT: "
                f"{'ENTAILED' if mc['entailed'] else 'NOT ENTAILED'}")
            lines.append(f"  Possible Models Checked: {mc['models_checked']}")
            lines.append(f"  Models Satisfying KB:    "
                         f"{mc['models_satisfying_kb']}")
            lines.append(f"  Models Entailing Query:  "
                         f"{mc['models_entailing_query']}")
            lines.append(
                f"CONSISTENT RESULT: "
                f"{'YES' if result.consistent else 'NO — DISCREPANCY'}")

        lines.extend(resolution.key_steps())
        return "\n".join(lines)

    # -- Convenience queries -------------------------------------------

    def ask_can_move(self, x: int, y: int, quiet: bool = False) -> AskResult:
        """ASK whether the rover may move into cell (x, y)."""
        return self.ask(f"CanMove_{x}_{y}", True, quiet=quiet)

    def ask_mission_complete(self, quiet: bool = True) -> bool:
        """ASK whether the mission-complete condition is entailed."""
        return bool(self.ask("MissionComplete", True,
                             use_model_checking=False, quiet=quiet))

    # ==================================================================
    # RETRACT
    # ==================================================================

    def retract(self, symbol: str, positive: bool = True,
                reason: str = "") -> bool:
        """
        RETRACT(KB, α) — remove an atomic sentence from the KB.

        Needed because some propositions are **fluents** — properties whose
        truth changes over time.  ``At_2_3`` is true only while the rover
        occupies (2,3); on moving, the old position fact must be retracted
        or the KB would claim the rover is in two places at once.

        Returns True if the sentence was present and has been removed.
        """
        literal = Literal(symbol, positive)
        if literal not in self._facts:
            return False

        self._facts.discard(literal)
        suffix = f"  ({reason})" if reason else ""
        self._say(f"  RETRACT: {literal}{suffix}", "retract")
        self._log.append(KBLogEntry("RETRACT", str(literal), reason))
        self._notify_change()
        return True

    # ==================================================================
    # INFER — forward chaining
    # ==================================================================

    def infer_forward(self, quiet: bool = False) -> List[str]:
        """
        Forward chaining:  Axioms → Inference Rules → New Facts.

        Repeatedly applies **Modus Ponens** to every rule whose antecedents
        are all satisfied, adding the consequent as a new fact, until no
        further facts can be derived (a fixed point).

            Hazard_2_4                        (fact)
            Hazard_2_4 → ¬MoveForward_2_4     (rule)
            ∴ ¬MoveForward_2_4                (derived by Modus Ponens)

        This is sound and complete for the definite-clause KB the rover
        builds, and it is what makes most ``ASK`` queries cheap.

        Returns:
            The list of newly derived sentences, as strings.
        """
        derived: List[str] = []
        changed = True

        while changed:
            changed = False
            for rule in self._rules:
                if not self._antecedents_satisfied(rule):
                    continue

                consequent = Literal(rule.consequent_symbol,
                                     rule.consequent_positive)
                if consequent in self._facts:
                    continue

                # Do not derive a fact that contradicts something already
                # known — that would make the KB inconsistent, and an
                # inconsistent KB entails everything (including unsafe moves).
                if consequent.negate() in self._facts:
                    if not quiet:
                        self._say(f"  INFERENCE BLOCKED: {rule} would derive "
                                  f"{consequent}, but {consequent.negate()} "
                                  f"is already known.", "result")
                    continue

                self._facts.add(consequent)
                derived.append(str(consequent))
                changed = True
                self._inference_count += 1
                self._clause_cache = None

                if not quiet:
                    premises = " ∧ ".join(
                        str(Literal(s, p)) for s, p in rule.antecedents)
                    self._say(f"  FORWARD CHAIN: {rule}", "infer")
                    self._say(f"    MODUS PONENS: [{premises}] ∧ [{rule}] "
                              f"∴ {consequent}", "infer")
                self._log.append(
                    KBLogEntry("INFER", str(consequent), f"via {rule}"))

        if derived:
            self._notify_change()
        return derived

    def _antecedents_satisfied(self, rule: Rule) -> bool:
        """True if every antecedent of the rule is currently believed."""
        return all(Literal(s, p) in self._facts for s, p in rule.antecedents)

    # ==================================================================
    # Backward reasoning (explanation mechanism)
    # ==================================================================

    def backward_explain(self, symbol: str, positive: bool = True) -> str:
        """
        Backward reasoning:  Goal → Required Conditions.

        Rather than deriving facts forward, this starts from a goal and
        reports which conditions would have to hold for it to follow, and
        whether each is currently known.

            GOAL: CanMove_2_4?
            Required:  Safe_2_4      ✓ KNOWN
                       ¬Hazard_2_4   ✓ KNOWN
                       ¬Radiation_2_4 ✗ UNKNOWN
            → CANNOT YET CONCLUDE CanMove_2_4

        Used as the explanation mechanism behind the "Why did the rover
        move?" panel; the actual decision is still made by resolution.
        """
        goal = Literal(symbol, positive)
        lines = [f"BACKWARD REASONING for goal: {goal}"]

        supporting = [r for r in self._rules
                      if r.consequent_symbol == symbol
                      and r.consequent_positive == positive]

        if not supporting:
            if goal in self._facts:
                lines.append(f"  {goal} is a DIRECT FACT in the KB "
                             f"(no derivation needed).")
            elif goal.negate() in self._facts:
                lines.append(f"  {goal.negate()} is a direct fact — "
                             f"{goal} is contradicted.")
            else:
                lines.append(f"  No rule concludes {goal}, and it is not a "
                             f"known fact — terrain not yet classified.")
            return "\n".join(lines)

        for rule in supporting:
            lines.append(f"  Supporting rule: {rule}")
            lines.append("  Required conditions:")
            all_known = True
            for sym, pos in rule.antecedents:
                literal = Literal(sym, pos)
                if literal in self._facts:
                    status = "✓ KNOWN"
                elif literal.negate() in self._facts:
                    status = "✗ CONTRADICTED"
                    all_known = False
                else:
                    status = "✗ UNKNOWN"
                    all_known = False
                lines.append(f"    {literal}: {status}")
            verdict = "CAN CONCLUDE" if all_known else "CANNOT YET CONCLUDE"
            lines.append(f"  → {verdict}: {goal}")

        return "\n".join(lines)

    # ==================================================================
    # Accessors
    # ==================================================================

    def get_facts(self) -> List[Literal]:
        """GET_FACTS() — every atomic sentence currently believed."""
        return sorted(self._facts)

    def get_rules(self) -> List[Rule]:
        """GET_RULES() — every implication currently believed."""
        return list(self._rules)

    def get_clauses(self) -> List[Clause]:
        """
        GET_CLAUSES() — the CNF clause set given to the resolution engine.

        Each fact becomes a unit clause; each rule becomes its CNF form.
        The result is cached and rebuilt only when the KB changes, because
        it is requested on every query and on every UI refresh.
        """
        if self._clause_cache is None:
            clauses: Set[Clause] = {Clause({lit}) for lit in self._facts}
            for rule in self._rules:
                clauses.update(rule.to_clauses())
            self._clause_cache = sorted(clauses, key=lambda c: (len(c), str(c)))
        return list(self._clause_cache)

    def get_clause_statistics(self) -> dict:
        """Break the clause set down by clause type (unit/Horn/definite/goal)."""
        return classify_clauses(self.get_clauses())

    def get_log(self) -> List[KBLogEntry]:
        return list(self._log)

    def get_recent_log(self, n: int = 20) -> List[KBLogEntry]:
        return self._log[-n:]

    def get_rule_schemas(self) -> List[Tuple[str, str, str]]:
        """The eight domain rule schemas, for display and documentation."""
        return list(RULE_SCHEMAS)

    def is_consistent(self) -> bool:
        """
        SATISFIABILITY check on the KB itself: does at least one model
        satisfy everything the rover believes?
        """
        positive = {lit.symbol for lit in self._facts if lit.positive}
        negative = {lit.symbol for lit in self._facts if not lit.positive}
        # A direct contradiction is the only way this KB can be unsatisfiable,
        # and `tell` already prevents it — but verify explicitly rather than
        # assume, since the claim matters for every entailment we report.
        if positive & negative:
            return False
        return self._model_checker.check_consistency(
            facts=positive, negated_facts=negative,
            rules=[r.to_model_check_tuple() for r in self._rules])

    @property
    def fact_count(self) -> int:
        return len(self._facts)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def clause_count(self) -> int:
        return len(self.get_clauses())

    @property
    def inference_count(self) -> int:
        return self._inference_count

    @property
    def resolution_count(self) -> int:
        return self._resolution_count

    @property
    def model_check_count(self) -> int:
        return self._model_check_count

    @property
    def models_enumerated(self) -> int:
        return self._model_checker.models_enumerated

    @property
    def tell_count(self) -> int:
        return self._tell_count

    @property
    def ask_count(self) -> int:
        return self._ask_count

    def reset(self) -> None:
        """Clear the KB completely — the rover starts knowing nothing."""
        self._facts.clear()
        self._rules.clear()
        self._rule_signatures.clear()
        self._log.clear()
        self._inference_count = 0
        self._resolution_count = 0
        self._model_check_count = 0
        self._tell_count = 0
        self._ask_count = 0
        self._clause_cache = None
        self._model_checker.reset_counters()
        self._notify_change()

    # ==================================================================
    # Domain rule constructors (instantiate the schemas for a cell)
    # ==================================================================

    def add_hazard_rules(self, x: int, y: int) -> None:
        """
        Rule 1:  Hazard_x_y → ¬MoveForward_x_y
        plus     Hazard_x_y → ¬CanMove_x_y

        The second form links the hazard to the proposition the decision
        procedure actually queries.
        """
        self.tell_rule(Rule([(f"Hazard_{x}_{y}", True)],
                            f"MoveForward_{x}_{y}", False,
                            f"Rule1-Hazard-{x}-{y}"))
        self.tell_rule(Rule([(f"Hazard_{x}_{y}", True)],
                            f"CanMove_{x}_{y}", False,
                            f"Rule1b-Hazard-NoCanMove-{x}-{y}"))

    def add_radiation_rules(self, x: int, y: int) -> None:
        """
        Rule 2:  Radiation_x_y → ¬Enter_x_y
        plus     Radiation_x_y → ¬CanMove_x_y
        """
        self.tell_rule(Rule([(f"Radiation_{x}_{y}", True)],
                            f"Enter_{x}_{y}", False,
                            f"Rule2-Radiation-{x}-{y}"))
        self.tell_rule(Rule([(f"Radiation_{x}_{y}", True)],
                            f"CanMove_{x}_{y}", False,
                            f"Rule2b-Radiation-NoCanMove-{x}-{y}"))

    def add_safe_canmove_rule(self, x: int, y: int) -> None:
        """
        Rule 3:  Safe_x_y ∧ ¬Hazard_x_y ∧ ¬Radiation_x_y → CanMove_x_y

        This is the *only* rule that can ever license a move, which is why
        an unclassified cell is never traversable: without ``Safe_x_y`` the
        antecedent cannot be satisfied.
        """
        self.tell_rule(Rule([(f"Safe_{x}_{y}", True),
                             (f"Hazard_{x}_{y}", False),
                             (f"Radiation_{x}_{y}", False)],
                            f"CanMove_{x}_{y}", True,
                            f"Rule3-CanMove-{x}-{y}"))

    def add_move_rule(self, from_x: int, from_y: int,
                      to_x: int, to_y: int) -> None:
        """
        Rule 4:  At_x_y ∧ CanMove_x2_y2 → MoveTo_x2_y2

        Ties the rover's current position fluent to the traversability of a
        neighbour, producing the concrete action proposition.
        """
        self.tell_rule(Rule([(f"At_{from_x}_{from_y}", True),
                             (f"CanMove_{to_x}_{to_y}", True)],
                            f"MoveTo_{to_x}_{to_y}", True,
                            f"Rule4-MoveTo-{to_x}-{to_y}"),
                       announce=False)

    def add_goal_rule(self, gx: int, gy: int) -> None:
        """Rule 5:  At_gx_gy → MissionComplete"""
        self.tell_rule(Rule([(f"At_{gx}_{gy}", True)],
                            "MissionComplete", True,
                            f"Rule5-Goal-{gx}-{gy}"))

    def add_unknown_investigate_rule(self, x: int, y: int) -> None:
        """
        Rule 6:  Unknown_x_y → Investigate_x_y

        Turns unclassified terrain into a *positive obligation to act*
        rather than a reason to stop: the rover derives Investigate_x_y and
        can then spend a sensor sweep to classify the cell.
        """
        self.tell_rule(Rule([(f"Unknown_{x}_{y}", True)],
                            f"Investigate_{x}_{y}", True,
                            f"Rule6-Investigate-{x}-{y}"),
                       announce=False)

    def add_perceive_hazard_rule(self, x: int, y: int) -> None:
        """Rule 7:  PerceiveHazard_x_y → Hazard_x_y"""
        self.tell_rule(Rule([(f"PerceiveHazard_{x}_{y}", True)],
                            f"Hazard_{x}_{y}", True,
                            f"Rule7-PerceiveHazard-{x}-{y}"),
                       announce=False)

    def add_perceive_radiation_rule(self, x: int, y: int) -> None:
        """Rule 8:  PerceiveRadiation_x_y → Radiation_x_y"""
        self.tell_rule(Rule([(f"PerceiveRadiation_{x}_{y}", True)],
                            f"Radiation_{x}_{y}", True,
                            f"Rule8-PerceiveRadiation-{x}-{y}"),
                       announce=False)

    # ==================================================================
    # High-level helpers used by the rover
    # ==================================================================

    def install_rules_for(self, x: int, y: int, status: str) -> None:
        """
        Install the domain rules that a terrain classification licenses.

        The *facts* come from the sensor (see :mod:`sensors`); this method
        supplies the *rules* that let the rover reason about them.  Keeping
        the two separate means there is exactly one place where perception
        becomes fact, and one place where the domain rules live.

        Args:
            status: SAFE | HAZARD | RADIATION | UNKNOWN | GOAL
        """
        if status == "SAFE":
            # Rule 3 — the only rule that can license entering a cell.
            self.add_safe_canmove_rule(x, y)

        elif status == "HAZARD":
            # Rule 7 turns the sensor reading into the hazard fact, and
            # Rule 1 turns the hazard fact into a movement prohibition.
            # Hazard_x_y is deliberately never TELLed directly — it is
            # *derived*, which is the perception → inference link this
            # project exists to demonstrate.
            self.add_perceive_hazard_rule(x, y)
            self.add_hazard_rules(x, y)

        elif status == "RADIATION":
            self.add_perceive_radiation_rule(x, y)   # Rule 8
            self.add_radiation_rules(x, y)           # Rule 2

        elif status == "UNKNOWN":
            self.add_unknown_investigate_rule(x, y)  # Rule 6

        elif status == "GOAL":
            # The goal cell is ordinary safe terrain that must be entered.
            self.add_safe_canmove_rule(x, y)

        else:
            raise ValueError(f"Unrecognised cell status: {status!r}")

    def tell_cell_status(self, x: int, y: int, status: str) -> None:
        """
        Convenience: assert a terrain classification *and* install its rules
        in one call.

        The rover normally TELLs sensor propositions directly and then calls
        :meth:`install_rules_for`; this helper covers the cases where a
        classification is known without a sensor event (the start cell, and
        the test suite).
        """
        self._say(f"\n  [KB] Cell ({x},{y}) classified as {status}", "tell")

        facts = {
            "SAFE": [(f"Safe_{x}_{y}", True), (f"Hazard_{x}_{y}", False),
                     (f"Radiation_{x}_{y}", False), (f"Unknown_{x}_{y}", False)],
            "HAZARD": [(f"PerceiveHazard_{x}_{y}", True),
                       (f"Safe_{x}_{y}", False), (f"Radiation_{x}_{y}", False),
                       (f"Unknown_{x}_{y}", False)],
            "RADIATION": [(f"PerceiveRadiation_{x}_{y}", True),
                          (f"Safe_{x}_{y}", False), (f"Hazard_{x}_{y}", False),
                          (f"Unknown_{x}_{y}", False)],
            "UNKNOWN": [(f"Unknown_{x}_{y}", True)],
            "GOAL": [(f"Goal_{x}_{y}", True), (f"Safe_{x}_{y}", True),
                     (f"Hazard_{x}_{y}", False), (f"Radiation_{x}_{y}", False),
                     (f"Unknown_{x}_{y}", False)],
        }.get(status)

        if facts is None:
            raise ValueError(f"Unrecognised cell status: {status!r}")

        for symbol, positive in facts:
            self.tell(symbol, positive)
        self.install_rules_for(x, y, status)

    def tell_at(self, x: int, y: int, previous: Optional[Tuple[int, int]] = None
                ) -> None:
        """
        Update the rover's position **fluent**.

        ``At_x_y`` is a fluent: true only of the current time step.  The
        previous position fact is retracted first, so the KB describes one
        successor state rather than accumulating every cell the rover has
        ever occupied.

            CURRENT STATE:   At_2_3
            ACTION:          MoveRight
            SUCCESSOR STATE: At_2_4    (At_2_3 retracted)
        """
        if previous is not None and previous != (x, y):
            self.retract(f"At_{previous[0]}_{previous[1]}", True,
                         reason="fluent superseded by successor state")
        self.tell(f"At_{x}_{y}", True)
