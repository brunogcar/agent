"""
tests/core/sleep_learn/test_feedback.py
Unit tests for the dynamic confidence scoring feedback loop.
"""
from unittest.mock import patch, MagicMock
from core.sleep_learn.feedback import update_rule_confidence

@patch('core.sleep_learn.feedback._get_collection')
def test_boosts_confidence_on_success(mock_get_col):
    """Successful traces should increase rule confidence by 0.1."""
    mock_col = MagicMock()
    mock_col.get.return_value = {'ids': ['rule1'], 'metadatas': [{'confidence_score': 0.8}]}
    mock_get_col.return_value = mock_col

    res = update_rule_confidence('rule1', success=True)
    
    assert res['status'] == 'updated'
    assert res['new_conf'] == 0.9
    mock_col.update.assert_called_once()

@patch('core.sleep_learn.feedback._get_collection')
def test_penalizes_confidence_on_failure(mock_get_col):
    """Failed traces should decrease rule confidence by 0.2."""
    mock_col = MagicMock()
    mock_col.get.return_value = {'ids': ['rule1'], 'metadatas': [{'confidence_score': 0.8}]}
    mock_get_col.return_value = mock_col

    res = update_rule_confidence('rule1', success=False)
    
    assert res['status'] == 'updated'
    assert res['new_conf'] == 0.6
    mock_col.update.assert_called_once()

@patch('core.sleep_learn.feedback._get_collection')
def test_purges_low_confidence_rule(mock_get_col):
    """Rules dropping below 0.3 confidence must be automatically purged."""
    mock_col = MagicMock()
    mock_col.get.return_value = {'ids': ['rule1'], 'metadatas': [{'confidence_score': 0.25}]}
    mock_get_col.return_value = mock_col

    res = update_rule_confidence('rule1', success=False)
    
    assert res['status'] == 'purged'
    mock_col.delete.assert_called_once_with(ids=['rule1'])
