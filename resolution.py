"""
resolution.py
=============
Propositional Resolution Inference Engine — the *syntactic* half of the
rover's reasoning.

The resolution rule
-------------------
From two clauses containing complementary literals, infer the clause made
of everything else::

    C₁ = P ∨ A ∨ B
    C₂ = ¬P ∨ D
    ------------------------
    resolvent = A ∨ B ∨ D

Proof by refutation
-------------------
To decide ``KB ⊨ α`` we do **not** try to derive α directly.  Instead we
add ¬α to the knowledge base and look for a contradiction::

    KB ⊨ α   iff   KB ∧ ¬α  is unsatisfiable

If repeated resolution derives the **empty clause** ``{}`` — a clause with
no literals, which cannot be satisfied by any model — then KB ∧ ¬α is
unsatisfiable and therefore KB ⊨ α.  If the clause set saturates (no new
clauses can be produced) without ever yielding ``{}``, then KB ⊭ α.

Soundness and completeness
--------------------------
The resolution rule is **sound**: every resolvent is a logical consequence
of its two parents, so anything derived is genuinely entailed
(KB ⊢ α ⟹ KB ⊨ α).

Resolution refutation is **complete** for propositional logic: if
KB ⊨ α then the empty clause *is* derivable (KB ⊨ α ⟹ KB ⊢ α).

Search strategy
---------------
Two strategies are implemented:

``set_of_support=True`` (default)
    Every resolution step must involve at least one clause descended from
    the negated query.  Resolving KB clauses against each other can never
    be what *starts* a refutation of ¬α, so those steps are pure waste;
    excluding them cuts the work by roughly an order of magnitude on this
    knowledge base.  Set-of-support resolution is refutation-complete
    **provided the KB itself is satisfiable** — which is exactly the
    guarantee :meth:`KnowledgeBase.tell` maintains and
    :meth:`KnowledgeBase.is_consistent` verifies.

``set_of_support=False``
    Unrestricted saturation: resolve every pair.  Complete without any
    side condition, and used by the test suite to confirm both strategies
    return the same answers.

Either way the ``max_clauses`` safety cutoff is reported explicitly in the
trace when it fires, rather than being silently returned as a negative
answer.

Other inference rules
---------------------
Modus Ponens, Modus Tollens and the unit-resolution/disjunctive rule are
all *special cases* of this one rule; :meth:`ResolutionEngine.demonstrate`
shows each of them as a single resolution step.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Set, Tuple

from logic import Clause, Literal


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------

class ResolutionResult:
    """The decision and the full reasoning trace of one resolution query."""

    def __init__(self,
                 query: str,
                 entailed: bool,
                 steps: List[str],
                 resolution_ops: int,
                 derived_empty: bool,
                 proof: Optional[List[str]] = None,
                 clause_count: int = 0,
                 iterations: int = 0,
                 cutoff: bool = False):
        self.query = query
        self.entailed = entailed
        self.steps = steps
        self.resolution_ops = resolution_ops
        self.derived_empty = derived_empty
        self.proof = proof or []
        self.clause_count = clause_count
        self.iterations = iterations
        self.cutoff = cutoff        # True if the safety limit stopped the search

    def key_steps(self, limit: int = 6) -> List[str]:
        """
        The most informative lines of the trace, for console display.

        For an entailed query this is the derivation chain that produced
        the empty clause; otherwise it is the tail of the search log.
        """
        if self.proof:
            return self.proof[:limit]
        return self.steps[-limit:]

    def full_trace(self) -> str:
        """The complete trace, newline-joined."""
        return "\n".join(self.steps)

    def __str__(self) -> str:
        status = "ENTAILED" if self.entailed else "NOT ENTAILED"
        return (f"QUERY: KB ⊨ {self.query} ?\n"
                f"RESULT: {status}\n"
                f"Resolution Operations: {self.resolution_ops}")

    def __bool__(self) -> bool:
        return self.entailed


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ResolutionEngine:
    """
    Resolution-based propositional theorem prover (AIMA §7.5).

    Usage::

        engine = ResolutionEngine()
        result = engine.resolve(kb_clauses, Literal("CanMove_2_3"))
        result.entailed        # bool
        result.proof           # the derivation of {} , if entailed
    """

    def __init__(self, max_clauses: int = 4000,
                 set_of_support: bool = True):
        """
        Args:
            max_clauses:    Safety cutoff on clause-set growth.  Resolution
                            can generate exponentially many clauses in the
                            worst case; hitting this limit is reported
                            explicitly in the trace.
            set_of_support: Use the set-of-support strategy (see the module
                            docstring).  False gives unrestricted saturation.
        """
        self.max_clauses = max_clauses
        self.set_of_support = set_of_support
        self.total_resolution_ops = 0
        self.queries_answered = 0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def resolve(self,
                kb_clauses: List[Clause],
                query_literal: Literal,
                set_of_support: Optional[bool] = None) -> ResolutionResult:
        """
        Decide ``KB ⊨ query_literal`` by refutation.

        Args:
            kb_clauses:     The KB in CNF.
            query_literal:  The literal being queried.
            set_of_support: Override the engine's default strategy.

        Returns:
            A :class:`ResolutionResult` carrying the decision, the number
            of resolution operations performed, and — when the query is
            entailed — the derivation chain that produced the empty clause.
        """
        self.queries_answered += 1
        use_sos = (self.set_of_support if set_of_support is None
                   else set_of_support)

        steps: List[str] = []
        resolution_ops = 0

        negated_query = query_literal.negate()
        negated_clause = Clause({negated_query})

        steps.append(f"QUERY: KB ⊨ {query_literal} ?")
        steps.append(f"NEGATED QUERY: {negated_query}")
        steps.append(f"REFUTATION: add [{negated_clause}] to the KB and "
                     f"search for the empty clause")

        # `base` holds the KB; `support` holds the negated query and every
        # clause derived from it.  With the set-of-support strategy, every
        # resolution step must involve a clause from `support`.
        base: Set[Clause] = set(kb_clauses)
        base.discard(negated_clause)
        support: Set[Clause] = {negated_clause}

        strategy = "set-of-support" if use_sos else "unrestricted saturation"
        steps.append(f"STRATEGY: {strategy}")
        steps.append(f"STARTING CLAUSE COUNT: {len(base) + 1}")

        # parents[c] = the two clauses that produced c, for proof extraction
        parents: Dict[Clause, Tuple[Clause, Clause]] = {}
        resolved_pairs: Set[frozenset] = set()

        iteration = 0
        while True:
            iteration += 1
            new_clauses: Set[Clause] = set()

            for ci, cj in self._candidate_pairs(base, support, use_sos):
                key = frozenset((ci, cj))
                if key in resolved_pairs:
                    continue
                resolved_pairs.add(key)

                resolvents = self._resolve_pair(ci, cj)
                resolution_ops += len(resolvents)
                self.total_resolution_ops += len(resolvents)

                for resolvent in resolvents:
                    if resolvent not in parents:
                        parents[resolvent] = (ci, cj)

                    if resolvent.is_empty():
                        # Contradiction → KB ∧ ¬α is unsatisfiable.
                        steps.append(
                            f"RESOLUTION STEP: [{ci}] + [{cj}] → {{}}")
                        steps.append("DERIVED: {}  (the empty clause)")
                        steps.append("CONCLUSION: KB ∧ ¬query is "
                                     "unsatisfiable ⟹ ENTAILED")
                        return ResolutionResult(
                            query=str(query_literal),
                            entailed=True,
                            steps=steps,
                            resolution_ops=resolution_ops,
                            derived_empty=True,
                            proof=self._extract_proof(
                                ci, cj, parents, query_literal),
                            clause_count=len(base) + len(support),
                            iterations=iteration)

                    new_clauses.add(resolvent)

            known = base | support
            truly_new = new_clauses - known

            if not truly_new:
                # Saturation: closed under resolution, no contradiction.
                if resolution_ops == 0:
                    steps.append(
                        f"NO RESOLUTION POSSIBLE: no clause in the KB "
                        f"contains {query_literal}, so the negated query "
                        f"has nothing to resolve against.")
                else:
                    steps.append(f"SATURATED after {iteration} iteration(s): "
                                 f"no new clauses derivable, empty clause "
                                 f"never produced")
                steps.append("CONCLUSION: NOT ENTAILED (KB ∧ ¬query is "
                             "satisfiable)")
                return ResolutionResult(
                    query=str(query_literal),
                    entailed=False,
                    steps=steps,
                    resolution_ops=resolution_ops,
                    derived_empty=False,
                    clause_count=len(known),
                    iterations=iteration)

            if len(known) + len(truly_new) > self.max_clauses:
                steps.append(f"SAFETY CUTOFF: clause set would exceed "
                             f"{self.max_clauses} clauses")
                steps.append("CONCLUSION: search abandoned — reported as NOT "
                             "ENTAILED (this is a resource limit, not a "
                             "logical result)")
                return ResolutionResult(
                    query=str(query_literal),
                    entailed=False,
                    steps=steps,
                    resolution_ops=resolution_ops,
                    derived_empty=False,
                    clause_count=len(known),
                    iterations=iteration,
                    cutoff=True)

            # Derived clauses join the set of support: they descend from ¬α.
            support |= truly_new

    def _candidate_pairs(self,
                         base: Set[Clause],
                         support: Set[Clause],
                         use_sos: bool):
        """
        Yield the clause pairs this strategy is allowed to resolve.

        Set-of-support: every pair includes a support clause.
        Unrestricted:   every pair in the whole clause set.
        """
        support_list = list(support)

        for i, ci in enumerate(support_list):
            for cj in support_list[i + 1:]:
                yield ci, cj
            for cj in base:
                yield ci, cj

        if use_sos:
            return

        base_list = list(base)
        for i, ci in enumerate(base_list):
            for cj in base_list[i + 1:]:
                yield ci, cj

    # ------------------------------------------------------------------
    # The resolution rule itself
    # ------------------------------------------------------------------

    def _resolve_pair(self, c1: Clause, c2: Clause) -> List[Clause]:
        """
        Apply the resolution rule to two clauses.

        For every complementary pair (P ∈ c1, ¬P ∈ c2) produce
        ``(c1 − {P}) ∪ (c2 − {¬P})``.

        Tautological resolvents are discarded: a clause containing both Q
        and ¬Q is true in every model, so it can never contribute to
        deriving a contradiction.
        """
        resolvents: List[Clause] = []
        for lit1 in c1.literals:
            complement = lit1.negate()
            if complement not in c2.literals:
                continue
            new_literals = ((c1.literals - {lit1}) |
                            (c2.literals - {complement}))
            resolvent = Clause(new_literals)
            if not resolvent.is_tautology():
                resolvents.append(resolvent)
        return resolvents

    # ------------------------------------------------------------------
    # Proof extraction
    # ------------------------------------------------------------------

    def _extract_proof(self,
                       c1: Clause,
                       c2: Clause,
                       parents: Dict[Clause, Tuple[Clause, Clause]],
                       query: Literal,
                       max_lines: int = 8) -> List[str]:
        """
        Walk back from the empty clause through the parent links to build a
        readable derivation, so the console shows *why* the query holds
        rather than merely that it does.
        """
        lines = [f"PROOF that KB ⊨ {query} (by refutation):",
                 f"  1. ASSUME ¬({query})  →  clause [{query.negate()}]"]

        chain: List[Tuple[Clause, Clause, Clause]] = []
        frontier: List[Clause] = []

        # The final step is always c1 + c2 → {}
        chain.append((c1, c2, Clause(set())))
        frontier.extend([c1, c2])

        seen: Set[Clause] = {c1, c2}
        while frontier and len(chain) < max_lines:
            clause = frontier.pop(0)
            if clause not in parents:
                continue
            p1, p2 = parents[clause]
            chain.append((p1, p2, clause))
            for parent in (p1, p2):
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)

        for index, (p1, p2, resolvent) in enumerate(reversed(chain), start=2):
            target = "{}" if resolvent.is_empty() else f"[{resolvent}]"
            lines.append(f"  {index}. RESOLVE [{p1}] with [{p2}]  →  {target}")

        lines.append(f"  ⟹ the empty clause {{}} is derived: KB ∧ ¬({query}) "
                     f"is unsatisfiable, therefore KB ⊨ {query}")
        return lines

    # ------------------------------------------------------------------
    # Classical inference rules as special cases of resolution
    # ------------------------------------------------------------------

    def demonstrate_modus_ponens(self, p: str = "P", q: str = "Q") -> str:
        """
        Modus Ponens::

            P → Q        (CNF:  ¬P ∨ Q)
            P
            ∴ Q

        One resolution step on P.
        """
        c1 = Clause({Literal(p, False), Literal(q, True)})
        c2 = Clause({Literal(p, True)})
        resolvents = self._resolve_pair(c1, c2)
        return "\n".join([
            "MODUS PONENS (as a single resolution step)",
            f"  Premise 1:  {p} → {q}    CNF: [{c1}]",
            f"  Premise 2:  {p}          CNF: [{c2}]",
            f"  Resolve on {p}:          → [{resolvents[0] if resolvents else '{}'}]",
            f"  ∴ {q}",
        ])

    def demonstrate_modus_tollens(self, p: str = "P", q: str = "Q") -> str:
        """
        Modus Tollens::

            P → Q        (CNF:  ¬P ∨ Q)
            ¬Q
            ∴ ¬P

        One resolution step on Q.
        """
        c1 = Clause({Literal(p, False), Literal(q, True)})
        c2 = Clause({Literal(q, False)})
        resolvents = self._resolve_pair(c1, c2)
        return "\n".join([
            "MODUS TOLLENS (as a single resolution step)",
            f"  Premise 1:  {p} → {q}    CNF: [{c1}]",
            f"  Premise 2:  ¬{q}         CNF: [{c2}]",
            f"  Resolve on {q}:          → [{resolvents[0] if resolvents else '{}'}]",
            f"  ∴ ¬{p}",
        ])

    def demonstrate_disjunctive_syllogism(self, p: str = "P",
                                          q: str = "Q") -> str:
        """
        Disjunctive syllogism (unit resolution)::

            P ∨ Q
            ¬P
            ∴ Q
        """
        c1 = Clause({Literal(p, True), Literal(q, True)})
        c2 = Clause({Literal(p, False)})
        resolvents = self._resolve_pair(c1, c2)
        return "\n".join([
            "DISJUNCTIVE SYLLOGISM (as a single resolution step)",
            f"  Premise 1:  {p} ∨ {q}    CNF: [{c1}]",
            f"  Premise 2:  ¬{p}         CNF: [{c2}]",
            f"  Resolve on {p}:          → [{resolvents[0] if resolvents else '{}'}]",
            f"  ∴ {q}",
        ])

    def demonstrate_all(self) -> str:
        """All three classical rules, shown as resolution steps."""
        return "\n\n".join([
            self.demonstrate_modus_ponens(),
            self.demonstrate_modus_tollens(),
            self.demonstrate_disjunctive_syllogism(),
        ])

    def reset_counters(self) -> None:
        """Zero the cumulative counters (used on simulation reset)."""
        self.total_resolution_ops = 0
        self.queries_answered = 0
