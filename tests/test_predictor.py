# Tests for a Predictor class.
# Pre-processors and the dataset are real, the model is real only where its output does not matter,
# for other scenarious a mock model is used.

import joblib
import numpy as np
import pandas as pd
import pytest

import prediction_module.predictor as predictor_module
from prediction_module.predictor import Predictor
from tests.conftest import PROJECT_ROOT
from tests.mock_env import MockXGBClassifier


# Replay pre-processing steps as in Jupyter Notebook where the model was trained
def replay_notebook_preprocessing(predictor, features):
    row = pd.DataFrame([features])
    row[predictor.numeric_cols] = row[predictor.numeric_cols].apply(pd.to_numeric, errors='coerce')
    for col, upper in predictor.clip_thresholds.items():
        row[col] = row[col].clip(upper=upper)
    row[predictor.numeric_cols] = predictor.num_imputer.transform(row[predictor.numeric_cols])
    row[predictor.categorical_cols] = predictor.cat_imputer.transform(row[predictor.categorical_cols])
    encoded = predictor.cat_encoder.transform(row[predictor.categorical_cols])
    encoded_names = predictor.cat_encoder.get_feature_names_out(predictor.categorical_cols)
    row = row.drop(columns=predictor.categorical_cols)
    for position, name in enumerate(encoded_names):
        row[name] = encoded[0, position]
    row[predictor.skewed_cols] = predictor.power_transformer.transform(row[predictor.skewed_cols].astype(float).values)
    return row[predictor.kept_features].to_numpy(dtype=float)


# Tests that rows of original dataset pre-processing is reproduced exactly as it was at training time
@pytest.mark.parametrize("row_index", [
    0,      # the first row
    500,    # a row from the middle
    900,    # a row from the end
])
def test_prepare_model_input_reproduces_notebook_preprocessing(real_predictor, dataset, row_index):
    raw_columns = real_predictor.numeric_cols + real_predictor.categorical_cols
    features = {col: dataset.iloc[row_index][col] for col in raw_columns}
    model_input = real_predictor.prepare_model_input(features)
    assert list(model_input.columns) == real_predictor.kept_features
    assert np.allclose(model_input.to_numpy(dtype=float), replay_notebook_preprocessing(real_predictor, features))


# Tests that NaN and None values are imputed for live features
def test_prepare_model_input_imputes_none_values(real_predictor, live_features):
    model_input = real_predictor.prepare_model_input(live_features)
    assert model_input.shape == (1, len(real_predictor.kept_features))
    assert not model_input.isna().any().any()


# Tests classification threshold (0.85), boundary is inclusive
@pytest.mark.parametrize("scam_probability, expected_prediction", [
    (0.84, 'normal'),   # right before 0.85
    (0.85, 'scam'),     # exactly at the threshold
    (0.99, 'scam'),     # clearly over the threshold
])
def test_predict_threshold(mock_model_predictor, live_features, scam_probability, expected_prediction):
    MockXGBClassifier.scam_probability = scam_probability
    result = mock_model_predictor.predict(live_features)
    assert result['scam_probability'] == pytest.approx(scam_probability)
    assert result['prediction'] == expected_prediction and result['error'] is None


# Tests that empty input returns dictionary with None results and an error message
@pytest.mark.parametrize("features", [
    None,               # nothing passed at all
    {},                 # empty dictionary
])
def test_predict_empty_input(mock_model_predictor, features):
    result = mock_model_predictor.predict(features)
    assert result == {'prediction': None, 'scam_probability': None, 'risk_signals': None,
                      'error': 'No features to predict on'}


# Tests that risk signals are reported properly
def test_get_risk_signals_selection(mock_model_predictor, live_features):
    kept = mock_model_predictor.kept_features
    contributions = np.full(len(kept) + 1, -0.1)
    contributions[-1] = 5.0                                                # bias term must be ignored
    contributions[kept.index('MaxPrice (Quarter 1)')] = 1.5                # strongest, but NaN in input, must be skipped
    contributions[kept.index('has_owner_guard')] = 0.9
    contributions[kept.index('project period (days)')] = 0.5
    contributions[kept.index('Blockchain Type_POS')] = 0.4
    contributions[kept.index('Holders_12h')] = 0.3                         # fourth, should be cut (top-3 are shown)
    MockXGBClassifier.contributions = contributions

    signals = mock_model_predictor.predict(live_features)['risk_signals']
    assert [s['feature'] for s in signals] == ['has_owner_guard', 'project period (days)', 'Blockchain Type_POS']
    assert signals[0]['value'] == 1 and signals[1]['value'] == 943
    assert signals[2]['value'] == 'POS'


# Tests that with no positive contributors (a clean token) the risk signal list is empty and prediction still returned
def test_get_risk_signals_no_positive_contributors(mock_model_predictor, live_features):
    MockXGBClassifier.contributions = np.full(len(mock_model_predictor.kept_features) + 1, -0.2)
    result = mock_model_predictor.predict(live_features)
    assert result['risk_signals'] == [] and result['scam_probability'] is not None


# Tests that inconsistent pre-processor with different column order is refused
def test_inconsistent_column_order_in_preprocessor(tmp_path):
    broken = joblib.load(PROJECT_ROOT / 'prediction_module' / 'models' / 'preprocessing.joblib')
    broken['xgboost_kept_features'] = list(reversed(broken['xgboost_kept_features']))
    broken_path = tmp_path / 'broken_preprocessing.joblib'
    joblib.dump(broken, broken_path)
    with pytest.raises(AssertionError, match='order'):
        Predictor(model_path=str(PROJECT_ROOT / 'prediction_module' / 'models' / 'xgboost_model.json'),
                  preprocessing_path=str(broken_path))


# Tests that a real dataset row produces probability score and a label is
# consistent with the threshold
def test_real_model_predictoin(real_predictor, dataset):
    raw_columns = real_predictor.numeric_cols + real_predictor.categorical_cols
    features = {col: dataset.iloc[0][col] for col in raw_columns}
    result = real_predictor.predict(features)
    assert result['error'] is None
    assert 0.0 <= result['scam_probability'] <= 1.0
    expected_label = 'scam' if result['scam_probability'] >= predictor_module.PREDICTION_THRESHOLD else 'normal'
    assert result['prediction'] == expected_label