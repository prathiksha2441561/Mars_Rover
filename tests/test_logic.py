"""
tests/test_logic.py
===================
Automated tests for the propositional logic layer.

Tests:
  1. CNF conversion (implication, biconditional, De Morgan's, double negation)
  2. Resolution engine (entailment, non-entailment, contradiction)
  3. KnowledgeBase TELL/ASK/RETRACT/INFER
  4. Classic inference rules (Modus Ponens, Modus Tollens, Disjunctive)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

from logic import (Literal, Clause, CNFConverter, atom, neg, impl, conj, disj, iff,
                   make_implication_clauses, make_conjunction_implication_clauses)
from resolution import ResolutionEngine
from knowledge_base import KnowledgeBase


# ===========================================================================
# 1. Literal and Clause tests
# ===========================================================================

class TestLiteral(unittest.TestCase):

    def test_positive_literal(self):
        lit = Literal("P", True)
        self.assertEqual(str(lit), "P")
        self.assertTrue(lit.positive)

    def test_negative_literal(self):
        lit = Literal("P", False)
        self.assertEqual(str(lit), "¬P")
        self.assertFalse(lit.positive)

    def test_negate(self):
        lit = Literal("Safe_2_3", True)
        neg_lit = lit.negate()
        self.assertFalse(neg_lit.positive)
        self.assertEqual(neg_lit.symbol, "Safe_2_3")

    def test_complement_of(self):
        p = Literal("P", True)
        not_p = Literal("P", False)
        q = Literal("Q", True)
        self.assertTrue(p.is_complement_of(not_p))
        self.assertTrue(not_p.is_complement_of(p))
        self.assertFalse(p.is_complement_of(q))

    def test_hashable_in_set(self):
        s = {Literal("P", True), Literal("P", False), Literal("Q", True)}
        self.assertEqual(len(s), 3)


class TestClause(unittest.TestCase):

    def test_empty_clause(self):
        c = Clause(set())
        self.assertTrue(c.is_empty())

    def test_unit_clause(self):
        c = Clause({Literal("P", True)})
        self.assertEqual(len(c), 1)
        self.assertFalse(c.is_empty())

    def test_tautology(self):
        c = Clause({Literal("P", True), Literal("P", False)})
        self.assertTrue(c.is_tautology())

    def test_non_tautology(self):
        c = Clause({Literal("P", True), Literal("Q", False)})
        self.assertFalse(c.is_tautology())

    def test_str(self):
        c = Clause(set())
        self.assertEqual(str(c), "{}")


# ===========================================================================
# 2. CNF Conversion tests
# ===========================================================================

class TestCNFConverter(unittest.TestCase):

    def setUp(self):
        self.converter = CNFConverter()

    def test_implication_elimination(self):
        """P → Q becomes ¬P ∨ Q"""
        expr = impl(atom("P"), atom("Q"))
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 1)
        clause = clauses[0]
        lits = clause.literals
        self.assertIn(Literal("P", False), lits)
        self.assertIn(Literal("Q", True), lits)

    def test_biconditional_elimination(self):
        """P ↔ Q becomes (P → Q) ∧ (Q → P)"""
        expr = iff(atom("P"), atom("Q"))
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 2)

    def test_double_negation(self):
        """¬¬P becomes P"""
        expr = neg(neg(atom("P")))
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 1)
        lits = clauses[0].literals
        self.assertIn(Literal("P", True), lits)
        self.assertNotIn(Literal("P", False), lits)

    def test_demorgan_and(self):
        """¬(P ∧ Q) becomes ¬P ∨ ¬Q"""
        expr = neg(conj(atom("P"), atom("Q")))
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 1)
        lits = clauses[0].literals
        self.assertIn(Literal("P", False), lits)
        self.assertIn(Literal("Q", False), lits)

    def test_demorgan_or(self):
        """¬(P ∨ Q) becomes ¬P ∧ ¬Q"""
        expr = neg(disj(atom("P"), atom("Q")))
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 2)

    def test_distribution_or_over_and(self):
        """P ∨ (Q ∧ R) becomes (P ∨ Q) ∧ (P ∨ R)"""
        expr = disj(atom("P"), conj(atom("Q"), atom("R")))
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 2)

    def test_conjunction_to_two_clauses(self):
        """P ∧ Q becomes two unit clauses"""
        expr = conj(atom("P"), atom("Q"))
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 2)

    def test_atom(self):
        """Single atom becomes unit clause"""
        expr = atom("Safe_2_3")
        clauses = self.converter.convert(expr)
        self.assertEqual(len(clauses), 1)
        self.assertIn(Literal("Safe_2_3", True), clauses[0].literals)


# ===========================================================================
# 3. Resolution Engine tests
# ===========================================================================

class TestResolutionEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ResolutionEngine()

    def test_modus_ponens_entailment(self):
        """
        P → Q  +  P  ⊨  Q

        Clauses:
          {¬P, Q}  (from P → Q)
          {P}      (P is true)
        Query: Q
        """
        clauses = [
            Clause({Literal("P", False), Literal("Q", True)}),  # ¬P ∨ Q
            Clause({Literal("P", True)}),                        # P
        ]
        result = self.engine.resolve(clauses, Literal("Q", True))
        self.assertTrue(result.entailed, "Q should be entailed by Modus Ponens")

    def test_modus_tollens_entailment(self):
        """
        P → Q  +  ¬Q  ⊨  ¬P
        """
        clauses = [
            Clause({Literal("P", False), Literal("Q", True)}),  # ¬P ∨ Q
            Clause({Literal("Q", False)}),                       # ¬Q
        ]
        result = self.engine.resolve(clauses, Literal("P", False))
        self.assertTrue(result.entailed, "¬P should be entailed by Modus Tollens")

    def test_disjunctive_syllogism(self):
        """
        P ∨ Q  +  ¬P  ⊨  Q
        """
        clauses = [
            Clause({Literal("P", True), Literal("Q", True)}),   # P ∨ Q
            Clause({Literal("P", False)}),                       # ¬P
        ]
        result = self.engine.resolve(clauses, Literal("Q", True))
        self.assertTrue(result.entailed, "Q should be entailed by Disjunctive Syllogism")

    def test_conjunctive_simplification(self):
        """
        P ∧ Q  ⊨  P
        """
        clauses = [
            Clause({Literal("P", True)}),
            Clause({Literal("Q", True)}),
        ]
        result = self.engine.resolve(clauses, Literal("P", True))
        self.assertTrue(result.entailed, "P should be directly entailed (unit clause)")

    def test_non_entailment(self):
        """
        P  ⊭  Q  (Q not entailed by just P)
        """
        clauses = [
            Clause({Literal("P", True)}),
        ]
        result = self.engine.resolve(clauses, Literal("Q", True))
        self.assertFalse(result.entailed, "Q should NOT be entailed by just P")

    def test_hazard_prevents_move(self):
        """
        Hazard_2_3  +  Hazard_2_3 → ¬MoveForward_2_3  ⊨  ¬MoveForward_2_3
        """
        clauses = [
            Clause({Literal("Hazard_2_3", True)}),
            Clause({Literal("Hazard_2_3", False), Literal("MoveForward_2_3", False)}),
        ]
        result = self.engine.resolve(clauses, Literal("MoveForward_2_3", False))
        self.assertTrue(result.entailed, "¬MoveForward should be entailed by hazard rule")

    def test_safe_allows_canmove(self):
        """
        Safe ∧ ¬Hazard ∧ ¬Radiation → CanMove
        When all three are satisfied, CanMove should be entailed.
        """
        clauses = [
            Clause({Literal("Safe_3_3", True)}),
            Clause({Literal("Hazard_3_3", False)}),
            Clause({Literal("Radiation_3_3", False)}),
            # Rule 3 as CNF: ¬Safe_3_3 ∨ Hazard_3_3 ∨ Radiation_3_3 ∨ CanMove_3_3
            Clause({Literal("Safe_3_3", False), Literal("Hazard_3_3", True),
                    Literal("Radiation_3_3", True), Literal("CanMove_3_3", True)}),
        ]
        result = self.engine.resolve(clauses, Literal("CanMove_3_3", True))
        self.assertTrue(result.entailed, "CanMove should be entailed when safe conditions hold")

    def test_contradiction_detection(self):
        """
        P  +  ¬P  → empty clause (contradiction)
        Query anything — the negated query will always resolve quickly.
        """
        clauses = [
            Clause({Literal("P", True)}),
            Clause({Literal("P", False)}),
        ]
        # Set-of-support is only guaranteed refutation-complete for a
        # SATISFIABLE KB (the guarantee KnowledgeBase.tell maintains in
        # practice). An inconsistent KB like this one needs unrestricted
        # saturation to find the contradiction, since it does not involve
        # the negated query at all.
        result = self.engine.resolve(clauses, Literal("Q", True),
                                     set_of_support=False)
        # Contradictory KB entails everything
        self.assertTrue(result.entailed)

    def test_resolution_ops_counted(self):
        """Resolution should count operations."""
        clauses = [
            Clause({Literal("P", False), Literal("Q", True)}),
            Clause({Literal("P", True)}),
        ]
        result = self.engine.resolve(clauses, Literal("Q", True))
        self.assertGreater(result.resolution_ops, 0)


# ===========================================================================
# 4. KnowledgeBase API tests
# ===========================================================================

class TestKnowledgeBase(unittest.TestCase):

    def setUp(self):
        self.kb = KnowledgeBase()

    def test_tell_positive(self):
        self.kb.tell("Safe_1_1", True)
        from logic import Literal
        self.assertIn(Literal("Safe_1_1", True), self.kb._facts)

    def test_tell_negative(self):
        self.kb.tell("Hazard_1_1", False)
        from logic import Literal
        self.assertIn(Literal("Hazard_1_1", False), self.kb._facts)

    def test_ask_direct_fact(self):
        self.kb.tell("Safe_2_2", True)
        entailed, _ = self.kb.ask("Safe_2_2", True, use_model_checking=False)
        self.assertTrue(entailed)

    def test_ask_negation_of_fact(self):
        self.kb.tell("Hazard_3_3", True)
        entailed, _ = self.kb.ask("Hazard_3_3", False, use_model_checking=False)
        self.assertFalse(entailed)

    def test_retract(self):
        self.kb.tell("Visited_1_1", True)
        self.kb.retract("Visited_1_1", True)
        from logic import Literal
        self.assertNotIn(Literal("Visited_1_1", True), self.kb._facts)

    def test_forward_chaining(self):
        """Forward chaining: Hazard → ¬CanMove should fire."""
        self.kb.tell("Hazard_4_4", True)
        self.kb.add_hazard_rules(4, 4)
        derived = self.kb.infer_forward()
        # ¬MoveForward_4_4 and ¬CanMove_4_4 should be derived
        self.assertTrue(any("MoveForward_4_4" in d for d in derived))

    def test_tell_cell_safe(self):
        self.kb.tell_cell_status(2, 2, "SAFE")
        from logic import Literal
        self.assertIn(Literal("Safe_2_2", True), self.kb._facts)
        self.assertIn(Literal("Hazard_2_2", False), self.kb._facts)

    def test_tell_cell_hazard(self):
        self.kb.tell_cell_status(3, 3, "HAZARD")
        from logic import Literal
        # Hazard_3_3 is not TELLed directly — it is DERIVED from the
        # PerceiveHazard_3_3 sensor fact by Rule 7 during forward chaining.
        self.assertIn(Literal("PerceiveHazard_3_3", True), self.kb._facts)
        self.assertIn(Literal("Safe_3_3", False), self.kb._facts)
        derived = self.kb.infer_forward()
        self.assertIn(Literal("Hazard_3_3", True), self.kb._facts)
        self.assertTrue(any("Hazard_3_3" in d for d in derived))

    def test_backward_explain(self):
        self.kb.tell_cell_status(1, 1, "SAFE")
        explanation = self.kb.backward_explain("CanMove_1_1", True)
        self.assertIn("CanMove_1_1", explanation)

    def test_kb_fact_count_increases(self):
        initial = self.kb.fact_count
        self.kb.tell("NewFact_5_5", True)
        self.assertGreater(self.kb.fact_count, initial)


# ===========================================================================
# 5. Make implication clauses helper tests
# ===========================================================================

class TestHelperFunctions(unittest.TestCase):

    def test_make_implication_clauses(self):
        """P → ¬Q becomes ¬P ∨ ¬Q"""
        clauses = make_implication_clauses("P", True, "Q", False)
        self.assertEqual(len(clauses), 1)
        lits = clauses[0].literals
        self.assertIn(Literal("P", False), lits)
        self.assertIn(Literal("Q", False), lits)

    def test_make_conjunction_implication(self):
        """(A ∧ B) → C becomes ¬A ∨ ¬B ∨ C"""
        clauses = make_conjunction_implication_clauses(
            [("A", True), ("B", True)], "C", True
        )
        self.assertEqual(len(clauses), 1)
        lits = clauses[0].literals
        self.assertIn(Literal("A", False), lits)
        self.assertIn(Literal("B", False), lits)
        self.assertIn(Literal("C", True), lits)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  MARS ROVER — LOGIC TESTS")
    print("=" * 60)
    unittest.main(verbosity=2)
