"""Hand-authored claims and mutations validate a bounded semantic rubric."""

from copy import deepcopy

import pytest

from flexresearch.report_narrative import result_narrative
from flexresearch.report_review import review_report_content


TOOL = 'a' * 32
HASH = 'b' * 64


def evidence():
    return {'status': 'complete', 'calculated_result': {'spectrum': {'dominant_frequency_hz': 1.2}}, 'trajectory': [{'tool_name': 'spectral_analysis', 'tool_run_id': TOOL, 'status': 'complete'}], 'source_refs': [{'tool_run_id': TOOL, 'source_sha256': HASH, 'channel': 'ch4'}]}


def report(prose=None):
    # Manually authored, not using the narrative renderer as its own oracle.
    prose = prose or f'通道 ch4：主要频率：1.2 Hz。不能据此作医学诊断。依据工具 `{TOOL}`。'
    sections = {'Experiment Metadata': 'SYNTHETIC test record', 'Data Quality': 'Finite samples only', 'Processing Methods': 'Mean removal and FFT', 'Figures & Derived Artifacts': 'No requested figures.', 'Measured Result': 'Raw samples were preserved.', 'Calculated Result': 'dominant_frequency_hz: 1.2', 'Agent Interpretation': prose, 'Limitations': 'Synthetic waveform; no human motion labels or medical validation.', 'Source & Provenance': HASH}
    return '\n\n'.join(f'## {heading}\n\n{body}' for heading, body in sections.items())


def test_hand_authored_paraphrase_passes_without_llm_judge():
    review = review_report_content(report(), [evidence()])
    assert review.status == 'supported_within_rubric'
    assert review.recognized_claim_count == 1 and review.human_review_required
    assert review.track == 'semantic_rule_based'


@pytest.mark.parametrize('old,new', [('1.2 Hz', '1.4 Hz'), ('1.2 Hz', '1.2 kHz'), ('ch4', 'ch5'), (TOOL, 'c'*32)])
def test_wrong_number_unit_channel_or_tool_fails_even_with_correct_json(old, new):
    good = report()
    # Mutate only interpretation, preserving the correct structured result.
    before, after = good.split('## Agent Interpretation\n\n')
    prose, rest = after.split('## Limitations', 1)
    changed = before + '## Agent Interpretation\n\n' + prose.replace(old, new) + '## Limitations' + rest
    review = review_report_content(changed, [evidence()])
    assert review.status == 'needs_revision'
    assert any(item.name == 'metric_and_source_support' and item.status == 'fail' for item in review.criteria)


def test_generic_explanation_does_not_pass_just_because_numbers_exist_in_json():
    review = review_report_content(report('已完成分析，不能用于医学诊断。'), [evidence()])
    assert review.status == 'needs_revision'
    assert any(item.name == 'result_explanation_completeness' and item.status == 'fail' for item in review.criteria)


def test_medical_claim_is_not_excused_by_negation_in_another_sentence():
    review = review_report_content(report()+ '\n', [evidence()])
    assert review.status == 'supported_within_rubric'
    changed = report().replace('## Limitations', '该信号可以诊断疾病。\n\n## Limitations')
    review = review_report_content(changed, [evidence()])
    assert review.status == 'needs_revision'


@pytest.mark.parametrize('replacement', ['', '- No limitations were recorded by the deterministic run.'])
def test_empty_or_boilerplate_limitations_fail(replacement):
    text = report().replace('Synthetic waveform; no human motion labels or medical validation.', replacement)
    assert review_report_content(text, [evidence()]).status == 'needs_revision'


def test_unknown_numeric_claim_is_unreviewed_not_silently_approved():
    text = report().replace('## Limitations', '心率为 72 bpm。\n\n## Limitations')
    review = review_report_content(text, [evidence()])
    assert review.status == 'needs_human_review'
    assert any(item.name == 'unrecognized_numeric_prose' and item.status == 'not_evaluated' for item in review.criteria)


def test_missing_provenance_and_failed_tool_cannot_support_numbers():
    source = evidence()
    source['source_refs'][0]['source_sha256'] = ''
    assert review_report_content(report(), [source]).status == 'needs_revision'
    assert '1.2' not in result_narrative(source)  # Missing hash not promoted.
    source = evidence()
    source['trajectory'][0]['status'] = 'error'
    assert review_report_content(report(), [source]).status == 'needs_revision'
    assert '1.2' not in result_narrative(source)


def test_partial_run_needs_explicit_disclosure():
    source = evidence()
    source['status'] = 'partial'
    assert review_report_content(report(), [source]).status == 'needs_revision'
    assert review_report_content(report(result_narrative(source)), [source]).status == 'supported_within_rubric'


def test_non_numeric_source_and_unknown_result_need_human_review():
    source = evidence()
    source['calculated_result']['spectrum']['dominant_frequency_hz'] = None
    text = result_narrative(source)
    assert '1.2' not in text and '没有' in text
    assert review_report_content(report(text), [source]).status == 'needs_human_review'


@pytest.mark.parametrize('category,field,tool,value,unit', [('bioz', 'magnitude_mean_ohm', 'calculate_bioz_features', 1250, 'Ω'), ('comparison', 'mean_delta', 'compare_experiments', 5, ''), ('signal_quality', 'flagged_point_count', 'analyze_signal', 401, '点')])
def test_other_scientific_families_and_actual_values(category, field, tool, value, unit):
    source = evidence()
    source['calculated_result'] = {category: {field: value}}
    source['trajectory'][0]['tool_name'] = tool
    prose = result_narrative(source)
    assert str(value) in prose and unit in prose
    assert review_report_content(report(prose), [source]).status == 'supported_within_rubric'


def test_multi_channel_bioz_representative_mean_cannot_cite_other_channel():
    source = evidence()
    source['calculated_result'] = {'bioz': {'magnitude_mean_ohm': 1250}}
    source['trajectory'][0]['tool_name'] = 'calculate_bioz_features'
    second = deepcopy(source['trajectory'][0])
    second['tool_run_id'] = 'd'*32
    source['trajectory'].append(second)
    source['source_refs'].append({'tool_run_id': 'd'*32, 'source_sha256': HASH, 'channel': 'ch5'})
    prose = result_narrative(source)
    assert f'`{TOOL}`' in prose and 'ch4' in prose
    wrong = prose.replace(TOOL, 'd'*32).replace('ch4', 'ch5')
    assert review_report_content(report(wrong), [source]).status == 'needs_revision'

