"""Artifact compatibility checks; run with python -m unittest -v."""

import json
import shutil
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote

import yaml

from visualization import EvaluationCardsApp, find_eval_card_data, find_upload_data, parse_card_run


class CardCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "PhaseI_Final" / "Team" / "Algorithm" / "hash_timestamp"
        self.run.mkdir(parents=True)
        self.claim = 'values = [1, 2, 3]\nassert max(values) == 3, "wrong maximum"\n'
        self.card = {
            "title": "Example", "description": "A claim", "organizations": ["Team"],
            "claim": {"python": self.claim},
            "symbols": {"score": {"metadata": {"display": True}}},
            "kwdagger": {"pipeline": {"nodes": {"evaluate": {
                "executable": "python evaluate.py", "algo_params": {"seed": 1},
            }}}, "result_node": "evaluate", "matrix": {"evaluate.seed": [1, 2]}},
        }
        self.write_card()
        self.write_json("verdict.json", {
            "result": "INCONCLUSIVE", "metrics": {"Accuracy": 0.9},
            "claim_aggregation_strategy": {"type": "all"},
            "evidence": {"available": 2}, "requested_work": {"processes": 3},
            "provenance": {"formalization": {"status": "partially_validated"}},
        })
        self.write_json("symbol_metadata.json", {"score": {
            "display": True, "display_name": "Accuracy",
            "define_metric": {"objective": "maximize", "aggregation_strategy": {"type": "mean"}},
        }})
        for index, status in enumerate(["VERIFIED", "FALSIFIED", "INCONCLUSIVE"]):
            self.write_json(f"results/{index}/verdict.json", {
                "status": status, "symbols": {"score": 0.9, "internal": 42},
                "timestamp": f"2026-10-14T12:00:0{index}",
            })

    def write_card(self):
        (self.run / "card.yaml").write_text(yaml.safe_dump(self.card))

    def write_json(self, name, data):
        path = self.run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def parse(self):
        return parse_card_run(self.run, "PhaseI_Final", "Team", "Algorithm")

    def test_claim_metrics_and_statuses(self):
        card = self.parse()
        self.assertEqual(card["claim"], self.claim)
        self.assertEqual((card["n_verified"], card["n_falsified"], card["n_inconclusive"]), (1, 1, 1))
        self.assertEqual(card["metric_rows"], [{"name": "Accuracy", "value": "0.9", "objective": "maximize", "aggregation": "mean"}])
        self.assertEqual(card["runs"][0]["display_rows"], [{"name": "Accuracy", "symbol": "score", "value": "0.9"}])
        self.assertEqual(len(card["runs"][0]["symbols_rows"]), 2)

    def test_pipeline_forms(self):
        self.assertEqual(self.parse()["pipeline_steps"][0]["step"], "evaluate")
        self.card["kwdagger"]["pipeline"] = "package.pipeline()"
        self.write_card()
        self.assertEqual(self.parse()["pipeline_reference"], "package.pipeline()")
        self.assertEqual(self.parse()["matrix_rows"][0]["key"], "evaluate.seed")
        self.card["pipeline"] = {"legacy": {"executable": "legacy-command"}}
        self.write_card()
        self.assertEqual(self.parse()["pipeline_steps"][0]["step"], "legacy")

    def test_reports_and_provenance(self):
        (self.run / "report.md").write_text("# Results\nVerified empirically.")
        self.write_json("provenance.json", {"team": "example"})
        self.write_json("theory.json", {"schema_version": 1})
        card = self.parse()
        self.assertTrue(card["report"].startswith("# Results"))
        sections = {s["title"]: json.loads(s["text"]) for s in card["context_sections"]}
        self.assertEqual(sections["Provenance"]["team"], "example")
        self.assertEqual(sections["Verdict provenance"]["formalization"]["status"], "partially_validated")
        self.assertEqual(sections["Theory"]["schema_version"], 1)

    def test_discovery_at_different_depths_and_wrapped_upload(self):
        for root in [self.root, self.root / "PhaseI_Final", self.run.parent, self.run]:
            with self.subTest(root=root):
                cards = find_eval_card_data(root)
                self.assertEqual(len(cards), 1)
                self.assertEqual(cards[0]["milestone"], "PhaseI_Final")
        self.assertEqual(len(find_upload_data(self.root)), 1)

    def test_old_results_without_optional_artifacts(self):
        for name in ["kwdagger", "symbols"]:
            self.card.pop(name, None)
        self.write_card()
        (self.run / "symbol_metadata.json").unlink()
        self.write_json("verdict.json", {"result": "VERIFIED"})
        card = self.parse()
        self.assertEqual(card["metric_rows"], [])
        self.assertEqual(card["pipeline_steps"], [])
        self.assertEqual(card["context_sections"], [])

    def test_app_default_and_local_fallback(self):
        app = EvaluationCardsApp(self.root, server="test-final")
        self.assertEqual(app.state.selected_filters["milestone"], ["PhaseI_Final"])
        (self.root / "PhaseI_Final").rename(self.root / "SelfEvaluation")
        app = EvaluationCardsApp(self.root, server="test-local")
        self.assertEqual(app.state.selected_filters["milestone"], [])
        self.assertEqual(len(app.state.filtered_cards), 1)

    def test_theory_validation_is_scoped_to_declaration(self):
        self.write_json("theory.json", {"entries": [
            {"id": "proved", "kind": "theorem", "declaration": "Package.proved",
             "formalization": {"system": "lean4"}},
            {"id": "draft", "kind": "conjecture", "declaration": "Package.draft",
             "formalization": {"system": "lean4"}, "statement": "axioms ['sorryAx']"},
            {"id": "other", "declaration": "Package.other", "formalization": {"system": "lean4"}},
            {"id": "informal", "kind": "theorem"},
        ]})
        self.write_json("attachments/formalization/validation.json", {
            "status": "validated", "declarations": {"Package.proved": ["propext"]},
            "scope": "Submitted package only", "empirical_limit": "No accuracy guarantee",
        })
        view = self.parse()["theory_view"]
        self.assertEqual([e["status"] for e in view["statements"]], [
            "Validated (saved receipt)", "Draft / sorryAx", "Formalization referenced", "Not formalized",
        ])
        fields = {f["name"]: f["value"] for f in view["receipts"][0]["fields"]}
        self.assertEqual(fields["Empirical limit"], "No accuracy guarantee")

    def test_theory_premises_are_linked_not_verified(self):
        self.write_json("theory.json", {
            "entries": [{"id": "T", "premises": [{"id": "assumed"}, {"id": "checked"}, {"id": "gap"}]}],
            "premise_links": [
                {"ref": "T::assumed", "relation": "assumes", "note": "IID target", "file": "code.py", "line": 7},
                {"ref": "T::checked", "relation": "checks"},
            ],
            "premise_coverage": [{"ref": "T", "premises": [{"id": "gap", "accounted": False}],
                                  "unaccounted": ["gap"]}],
        })
        statement = self.parse()["theory_view"]["statements"][0]
        self.assertEqual(statement["linked_count"], 2)
        self.assertEqual([p["accounting"] for p in statement["premises"]], ["Linked", "Linked", "Unaccounted"])
        self.assertEqual(statement["premises"][0]["links"][0]["relation"], "assumes")
        self.assertEqual(statement["premises"][0]["links"][0]["source"], "code.py:7")

    def test_partial_validation_at_alternate_location_without_coverage(self):
        self.write_json("theory.json", {
            "entries": [{"id": "T", "declaration": "T", "formalization": {"system": "lean4"},
                         "premises": [{"id": "p"}]}],
            "premise_links": [{"ref": "T::p", "relation": "assumes"}],
        })
        self.write_json("attachments/validation.json", {
            "status": "partially_validated", "axioms": {"T": []}, "full_package_rebuilt": False,
        })
        view = self.parse()["theory_view"]
        self.assertEqual(view["statements"][0]["status"], "Partial validation")
        self.assertEqual(view["statements"][0]["linked_count"], 1)
        self.assertEqual(len(find_upload_data(self.root)[0]["theory_view"]["receipts"]), 1)

    def test_theory_missing_empty_and_inline(self):
        self.assertFalse(self.parse()["theory_view"]["available"])
        self.write_json("theory.json", {"schema_version": 1, "entries": []})
        view = self.parse()["theory_view"]
        self.assertTrue(view["available"])
        self.assertEqual(view["statements"], [])
        (self.run / "theory.json").unlink()
        self.card["theory"] = {"links": [{"ref": "External.T", "relation": "tests", "note": "Held-out test"}]}
        self.write_card()
        statement = self.parse()["theory_view"]["statements"][0]
        self.assertEqual(statement["id"], "External.T")
        self.assertEqual(statement["links"][0]["note"], "Held-out test")

    def test_routes_resolve_against_full_catalog_and_validate_tabs(self):
        self.write_json("theory.json", {"entries": [{"id": "T", "kind": "theorem"}]})
        app = EvaluationCardsApp(self.root, server="test-routes")
        card = app.state.cards[0]
        self.assertEqual(unquote(card["route_path"].split("/")[2]), card["route_key"])
        self.assertEqual({r["path"] for r in app.state.trame__routes}, {
            "/", "/cards/:cardId/:tab?", "/:pathMatch(.*)*",
        })
        app.state.selected_filters = {"organization": ["Another team"]}
        app.on_filter_change("", app.state.selected_filters)
        self.assertEqual(app.state.filtered_cards, [])
        app.on_route_change(card["route_key"], "theory")
        self.assertEqual(app.state.selected_card["id"], card["id"])
        self.assertEqual(app.state.current_tab, "theory")
        self.assertEqual(app.state.route_error, "")
        app.on_route_change(card["id"], "runs")
        self.assertEqual(app.state.current_tab, "runs")
        app.on_route_change(card["id"], "figures")
        self.assertIn("not available", app.state.route_error)
        app.on_route_change("missing", "theory")
        self.assertIsNone(app.state.selected_card)
        self.assertIn("not found", app.state.route_error)
        app.on_route_change()
        self.assertEqual(app.state.route_error, "")
        self.assertIsNone(app.state.selected_card)

    def test_named_routes_distinguish_runs_and_preserve_legacy_links(self):
        self.card["name"] = "shared name/#?"
        self.write_card()
        first = self.parse()
        self.assertTrue(first["route_key"].startswith("shared name/#?--"))
        self.assertEqual(unquote(first["route_base"].split("/")[2]), first["route_key"])
        self.assertEqual(first["route_key"], self.parse()["route_key"])
        other = self.run.with_name("hash_later")
        shutil.copytree(self.run, other)
        second = parse_card_run(other, "PhaseI_Final", "Team", "Algorithm")
        self.assertNotEqual(first["route_key"], second["route_key"])
        app = EvaluationCardsApp(self.root, server="test-named-routes")
        for card in (first, second):
            app.on_route_change(card["route_key"])
            self.assertEqual(app.state.selected_card["id"], card["id"])
            app.on_route_change(card["id"])
            self.assertEqual(app.state.selected_card["id"], card["id"])
        self.card.pop("name")
        self.write_card()
        self.assertTrue(self.parse()["route_key"].startswith("Algorithm--"))


if __name__ == "__main__":
    unittest.main()
