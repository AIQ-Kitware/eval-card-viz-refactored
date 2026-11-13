"""Optional native evidence survives directory and upload ingestion."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visualization import find_eval_card_data, find_upload_data, parse_card_run


def make_record(path):
    path.mkdir(parents=True)
    (path / 'results/cell').mkdir(parents=True)
    (path / 'card.yaml').write_text('''title: Example
description: Example claim
claim:
  python: "assert max(a, b) < 5, 'Both must pass'"
kwdagger:
  result_node: estimate
''')
    (path / 'verdict.json').write_text(json.dumps({
        'result': 'VERIFIED', 'metrics': {'Prediction error': 2.5},
        'provenance': {'theory_sources': {'nodes/estimate.py': {
            'url': 'https://example.org/revision/nodes/estimate.py'}}}}))
    (path / 'results/cell/verdict.json').write_text(json.dumps({
        'status': 'VERIFIED', 'symbols': {'a': 2, 'b': 3},
        'evidence': {'metrics.estimate.n_problems': 12,
                     'metrics.estimate.error': 2.5, 'metrics.ancestor.other': 99}}))
    (path / 'variants.json').write_text(json.dumps({'Model A': {'claims': ['cell']}}))
    (path / 'theory.json').write_text(json.dumps({
        'entries': [{'id': 'Example.law', 'kind': 'conjecture', 'statement': 'A prediction.'}],
        'statement_links': [{'ref': 'Example.law', 'relation': 'tests',
                             'file': 'nodes/estimate.py', 'line': 12}],
        'premise_links': [{'ref': 'Example.law::h', 'relation': 'assumes'}]}))
    return path


def test_variants_metrics_and_complete_claim_survive_serialization(tmp_path):
    result = json.loads(json.dumps(parse_card_run(make_record(tmp_path / 'run'), 'phase', 'org')))
    assert result['runs'][0]['label'] == 'Model A'
    assert result['metrics'] == {'Prediction error': 2.5}
    assert result['runs'][0]['measurement_rows'] == [
        {'name': 'n_problems', 'value': '12'}, {'name': 'error', 'value': '2.5'}]
    assert result['claim'] == "assert max(a, b) < 5, 'Both must pass'"


def test_informal_theory_keeps_relations_without_inventing_validation(tmp_path):
    result = parse_card_run(make_record(tmp_path / 'run'), 'phase', 'org')
    assert result['has_theory'] is True and result['has_formalization'] is False
    assert result['theory_links'][0]['relation'] == 'tests'
    assert result['theory_links'][0]['url'] == 'https://example.org/revision/nodes/estimate.py#L12'
    assert result['theory_links'][1]['relation'] == 'assumes'
    assert result['theory_links'][1]['url'] == ''


def test_directory_and_native_upload_layouts_have_the_same_evidence(tmp_path):
    root = tmp_path / 'repository'
    folder = root / 'phase/org/card'
    make_record(folder / 'run')
    from_repository = find_eval_card_data(root)[0]
    from_upload = find_upload_data(folder)[0]
    for key in ['theory', 'variants', 'metrics', 'runs', 'claim']:
        assert from_repository[key] == from_upload[key]
