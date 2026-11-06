"""The dashboard preserves recorded formal evidence without inferring validation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visualization import parse_card_run


def record(tmp_path):
    (tmp_path / 'results').mkdir()
    (tmp_path / 'card.yaml').write_text('title: Example\ndescription: Example claim\n')
    (tmp_path / 'verdict.json').write_text(json.dumps({'result': 'VERIFIED'}))
    return tmp_path


def test_legacy_result_has_no_invented_formalization(tmp_path):
    result = parse_card_run(record(tmp_path), 'campaign', 'organization')
    assert result['formalization'] == {} and result['theory'] == {}
    assert result['has_formalization'] is False


def test_validation_and_theory_survive_dashboard_serialization(tmp_path):
    path = record(tmp_path)
    formalization = {'status': 'validated', 'submission_revision': 'fixture',
                     'empirical_limit': 'The empirical prediction remains a measurement.'}
    provenance = {'formalization': formalization, 'other_evidence': 'retained'}
    (path / 'verdict.json').write_text(json.dumps({'result': 'VERIFIED', 'provenance': provenance}))
    theory = {'entries': [{'id': 'Example.theorem', 'premises': [{'id': 'h', 'statement': 'An assumption'}]}]}
    (path / 'theory.json').write_text(json.dumps(theory))
    result = json.loads(json.dumps(parse_card_run(path, 'campaign', 'organization')))
    assert result['formalization'] == formalization
    assert result['theory'] == theory and result['provenance'] == provenance
    assert result['has_formalization'] is True
    assert result['result'] == 'VERIFIED'


def test_theory_reference_alone_does_not_imply_validation(tmp_path):
    path = record(tmp_path)
    (path / 'theory.json').write_text(json.dumps({'entries': [
        {'id': 'Example.theorem', 'formalization': {'system': 'lean4'}}]}))
    result = parse_card_run(path, 'campaign', 'organization')
    assert result['has_formalization'] is True
    assert 'status' not in result['formalization']


def test_informal_theory_is_not_labelled_a_formalization(tmp_path):
    path = record(tmp_path)
    (path / 'theory.json').write_text(json.dumps({'entries': [{'id': 'Example.question'}]}))
    result = parse_card_run(path, 'campaign', 'organization')
    assert result['theory']['entries']
    assert result['has_formalization'] is False
