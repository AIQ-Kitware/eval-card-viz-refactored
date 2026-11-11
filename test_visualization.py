"""Artifact compatibility checks; run with python -m unittest -v."""

import json
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
