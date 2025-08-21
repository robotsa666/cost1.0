import unittest
from backend.app import allocate_costs, validate_tree

class AllocationTests(unittest.TestCase):
    def test_simple_chain_full_allocation(self):
        coa = [
            {"account_id": "100", "parent_id": "", "name": "Root"},
            {"account_id": "110", "parent_id": "100", "name": "A"},
            {"account_id": "120", "parent_id": "100", "name": "B"},
            {"account_id": "121", "parent_id": "120", "name": "B1"},
            {"account_id": "122", "parent_id": "120", "name": "B2"},
        ]
        costs = [{"account_id": "100", "amount": "100000"}]
        alloc = [
            {"parent_id": "100", "child_id": "110", "weight": "0.4"},
            {"parent_id": "100", "child_id": "120", "weight": "0.6"},
            {"parent_id": "120", "child_id": "121", "weight": "0.3"},
            {"parent_id": "120", "child_id": "122", "weight": "0.7"},
        ]
        out, _ = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        self.assertAlmostEqual(m.get("110", 0.0), 40000.0, places=2)
        self.assertAlmostEqual(m.get("121", 0.0), 18000.0, places=2)
        self.assertAlmostEqual(m.get("122", 0.0), 42000.0, places=2)
        self.assertAlmostEqual(m.get("100", 0.0), 0.0, places=2)
        self.assertAlmostEqual(m.get("120", 0.0), 0.0, places=2)

    def test_parent_without_keys_keeps_amount(self):
        coa = [
            {"account_id": "200", "parent_id": "", "name": "Root2"},
            {"account_id": "210", "parent_id": "200", "name": "C"},
            {"account_id": "220", "parent_id": "200", "name": "D"},
        ]
        costs = [{"account_id": "200", "amount": "100"}]
        alloc = []
        out, _ = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        self.assertAlmostEqual(m.get("200", 0.0), 100.0, places=6)
        self.assertAlmostEqual(m.get("210", 0.0), 0.0, places=6)
        self.assertAlmostEqual(m.get("220", 0.0), 0.0, places=6)

    def test_weights_as_percent_or_ratio(self):
        coa = [
            {"account_id": "300", "parent_id": "", "name": "R"},
            {"account_id": "310", "parent_id": "300", "name": "E"},
            {"account_id": "320", "parent_id": "300", "name": "F"},
        ]
        costs = [{"account_id": "300", "amount": "100"}]
        alloc = [
            {"parent_id": "300", "child_id": "310", "weight": "40"},
            {"parent_id": "300", "child_id": "320", "weight": "60"},
        ]
        out, _ = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        self.assertAlmostEqual(m.get("310", 0.0), 40.0, places=6)
        self.assertAlmostEqual(m.get("320", 0.0), 60.0, places=6)

    def test_allocation_to_non_child_is_ignored(self):
        coa = [
            {"account_id": "400", "parent_id": "", "name": "R"},
            {"account_id": "410", "parent_id": "400", "name": "G"},
        ]
        costs = [{"account_id": "400", "amount": "50"}]
        alloc = [{"parent_id": "400", "child_id": "999", "weight": "1"}]
        out, notes = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        self.assertAlmostEqual(m.get("400", 0.0), 50.0, places=6)
        self.assertTrue(any("brak dzieci" in n.lower() or "wagi" in n.lower() for n in notes))

    def test_validate_tree_cycle_and_bad_parent(self):
        coa = [
            {"account_id": "1", "parent_id": "2", "name": "A"},
            {"account_id": "2", "parent_id": "1", "name": "B"},
            {"account_id": "3", "parent_id": "999", "name": "C"},
        ]
        ok, msgs = validate_tree(coa)
        self.assertFalse(ok)
        self.assertTrue(any("cykl" in m.lower() for m in msgs))
        self.assertTrue(any("parent_id" in m.lower() for m in msgs))

    def test_decimal_comma_and_space(self):
        coa = [
            {"account_id": "10", "parent_id": "", "name": "R"},
            {"account_id": "11", "parent_id": "10", "name": "C1"},
            {"account_id": "12", "parent_id": "10", "name": "C2"},
        ]
        costs = [{"account_id": "10", "amount": "1 234,56"}]
        alloc = [
            {"parent_id": "10", "child_id": "11", "weight": "1"},
            {"parent_id": "10", "child_id": "12", "weight": "1"},
        ]
        out, _ = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        assert round(m.get("11", 0.0), 2) == 617.28
        assert round(m.get("12", 0.0), 2) == 617.28

    def test_zero_sum_weights_keep_on_parent(self):
        coa = [
            {"account_id": "20", "parent_id": "", "name": "R"},
            {"account_id": "21", "parent_id": "20", "name": "C1"},
        ]
        costs = [{"account_id": "20", "amount": "10"}]
        alloc = [{"parent_id": "20", "child_id": "21", "weight": "0"}]
        out, notes = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        self.assertAlmostEqual(m.get("20", 0.0), 10.0, places=6)
        self.assertTrue(any("wagi" in n.lower() for n in notes))

    def test_multiple_initial_cost_rows_are_aggregated(self):
        coa = [
            {"account_id": "30", "parent_id": "", "name": "R"},
            {"account_id": "31", "parent_id": "30", "name": "C1"},
        ]
        costs = [
            {"account_id": "30", "amount": "5"},
            {"account_id": "30", "amount": "7"},
        ]
        alloc = [{"parent_id": "30", "child_id": "31", "weight": "1"}]
        out, _ = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        self.assertAlmostEqual(m.get("31", 0.0), 12.0, places=6)
        self.assertAlmostEqual(m.get("30", 0.0), 0.0, places=6)

    def test_parent_with_keys_but_no_children(self):
        coa = [{"account_id": "40", "parent_id": "", "name": "R"}]
        costs = [{"account_id": "40", "amount": "9"}]
        alloc = [{"parent_id": "40", "child_id": "999", "weight": "1"}]
        out, notes = allocate_costs(coa, costs, alloc)
        m = {r["account_id"]: float(r["amount"]) for r in out}
        self.assertAlmostEqual(m.get("40", 0.0), 9.0, places=6)
        self.assertTrue(any("brak dzieci" in n.lower() for n in notes))

if __name__ == "__main__":
    unittest.main()
