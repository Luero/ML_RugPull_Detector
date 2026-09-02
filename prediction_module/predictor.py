# Predictor class takes pre-processors and a trained model at time of initialisation, then applies pre-processors to
# incoming data (extracted features) and makes a prediction.

import math

import joblib
import pandas as pd
import xgboost as xgb

# Paths to the model and pre-processor
MODEL_PATH = 'prediction_module/models/xgboost_model.json'
PREPROCESSING_PATH = 'prediction_module/models/preprocessing.joblib'

# Probability threshold to convert scam probability into class
# 0.58 was found empirically by deriving a threshold that maximises F1 from cross-validated training predictions
# (see 'Experimentation pipeline and model training.ipyng')
PREDICTION_THRESHOLD = 0.58

# Number of top risk signals returned with a prediction
TOP_RISK_SIGNALS_COUNT = 3

# Descriptions of features to display to a user as risk signals
RISK_SIGNAL_DESCRIPTIONS = {
    'MaxPrice (Quarter 1)': "Maximum price during the first quarter of the project's observed lifetime",
    'MaxPrice (Quarter 2)': "Maximum price during the second quarter of the project's observed lifetime",
    'the number of Transactions': 'Total number of token transfers',
    'Number of holders': 'Number of token holders',
    'Google results for project website (first day)': "Number of Google search results for the project's website at the first day of trading activity",
    'Google results for project x profile (first days)': "Number of Google search results for the project's X profile at the first day of trading activity",
    'Google results for project x profile (duration/2)': "Number of Google search results for the project's X profile at the project's lifetime midpoint",
    'project period (days)': 'Project lifetime in days',
    'Holders_12h': 'Number of holders 12 hours after deployment',
    'Holders_24h': 'Number of holders 24 hours after deployment',
    'has_contract_swap_patterns': 'Contract source code contains a function to swap its token balance to base cryptocurrency',
    'has_owner_guard': 'Contract source code contains functions to restrict swaps only to privileged accounts',
    'Blockchain Type_POS': 'Deployed on a proof-of-stake chain like Ethereum',
    'Blockchain Type_POSA': 'Deployed on a proof-of-staked-authority chain like BSC',
}

# Raw source columns for one-hot encoded features, to look up the extracted value reported in risk signals
ENCODED_FEATURE_SOURCES = {'Blockchain Type_POS': 'Blockchain Type', 'Blockchain Type_POSA': 'Blockchain Type'}


# Take a dictionary of extracted features and return scam probability with a class label
class Predictor:
    # Model and pre-processors are loaded once and reused for all predictions
    def __init__(self, model_path=MODEL_PATH, preprocessing_path=PREPROCESSING_PATH):
        self.model = xgb.XGBClassifier()
        self.model.load_model(model_path)
        preprocessors = joblib.load(preprocessing_path)
        self.clip_thresholds = preprocessors['clip_thresholds']
        self.num_imputer = preprocessors['num_imputer']
        self.cat_imputer = preprocessors['cat_imputer']
        self.cat_encoder = preprocessors['cat_encoder']
        self.power_transformer = preprocessors['power_transformer']
        self.skewed_cols = preprocessors['skewed_cols']
        self.numeric_cols = preprocessors['numeric_cols']
        self.categorical_cols = preprocessors['categorical_cols']
        self.full_feature_names = preprocessors['full_feature_names']
        self.kept_features = preprocessors['xgboost_kept_features']
        self.class_mapping = preprocessors['class_mapping']
        self.scam_class_index = self.class_mapping['scam']
        self.validate_model_and_preprocessors()


    # Validate that loaded model and pre-processors are consistent with each other when Predictor starts running
    def validate_model_and_preprocessors(self):
        assert 'class' not in self.numeric_cols, "numeric_cols contains the class label"
        assert set(self.kept_features) <= set(self.full_feature_names), "Kept features are missing from the full feature set"
        assert self.kept_features == [f for f in self.full_feature_names if f in set(self.kept_features)], \
            "Kept features order differs from training column order"
        assert self.model.n_features_in_ == len(self.kept_features), "Model feature count differs from the kept features list"


    # Replay pre-processing from model training extracted features
    def prepare_model_input(self, features):
        raw_columns = self.numeric_cols + self.categorical_cols
        unexpected_features = [name for name in features if name not in raw_columns]
        if unexpected_features:
            print(f"Ignoring extracted features unused by the model: {unexpected_features}")
        live_data = pd.DataFrame([{col: features.get(col) for col in raw_columns}])
        # Failed extractions (None) are treated as missing values
        live_data[self.numeric_cols] = live_data[self.numeric_cols].apply(pd.to_numeric, errors='coerce')

        for col, upper in self.clip_thresholds.items():
            live_data[col] = live_data[col].clip(upper=upper)

        live_data[self.numeric_cols] = self.num_imputer.transform(live_data[self.numeric_cols])
        live_data[self.categorical_cols] = self.cat_imputer.transform(live_data[self.categorical_cols])
        cat_array = self.cat_encoder.transform(live_data[self.categorical_cols])
        cat_feature_names = self.cat_encoder.get_feature_names_out(self.categorical_cols)
        cat_df = pd.DataFrame(cat_array, columns=cat_feature_names, index=live_data.index)
        live_data = live_data.drop(columns=self.categorical_cols)
        for col in cat_df.columns:
            live_data[col] = cat_df[col]
        live_data[self.skewed_cols] = self.power_transformer.transform(live_data[self.skewed_cols].astype(float).values)

        model_input = live_data.reindex(columns=self.kept_features)
        # Can happen only on schema bug, thus, return None
        if model_input.isna().any().any():
            print(f"Model input contains missing values after pre-processing: {model_input.columns[model_input.isna().any()].tolist()}")
            return None

        return model_input


    # Explain prediction with features that influence most to the result.
    # Uses SHAP values computed for an input row
    # Reference: https://xgboost.readthedocs.io/en/stable/prediction.html
    def get_risk_signals(self, model_input, features):
        contributions = self.model.get_booster().predict(xgb.DMatrix(model_input.to_numpy()), pred_contribs=True)[0]
        feature_contributions = list(zip(self.kept_features, contributions[:-1]))
        feature_contributions.sort(key=lambda item: item[1], reverse=True)

        risk_signals = []
        for feature, contribution in feature_contributions:
            if len(risk_signals) == TOP_RISK_SIGNALS_COUNT:
                break
            # Only features that lead to 'scam' verdict are risk signals
            if contribution <= 0:
                break
            source_column = ENCODED_FEATURE_SOURCES.get(feature, feature)
            raw_value = features.get(source_column)
            # Imputed features are not reported, since their values are synthetic (imputed by pre-processing, not obtained from feature extraction)
            if raw_value is None or (isinstance(raw_value, float) and math.isnan(raw_value)):
                continue
            risk_signals.append({
                'feature': feature,
                'description': RISK_SIGNAL_DESCRIPTIONS[feature],
                'value': raw_value,
            })

        return risk_signals


    # Make a prediction based on extracted features
    # Return 'prediction' ('scam' or 'normal'), 'scam_probability' (float between 0 and 1), 'risk_signals' and 'error' (if any)
    def predict(self, features):
        if not features:
            return {'prediction': None, 'scam_probability': None, 'risk_signals': None, 'error': 'No features to predict on'}
        model_input = self.prepare_model_input(features)
        if model_input is None:
            return {'prediction': None, 'scam_probability': None, 'risk_signals': None, 'error': 'Features could not be pre-processed'}
        scam_probability = float(self.model.predict_proba(model_input.to_numpy())[0, self.scam_class_index])
        prediction = 'scam' if scam_probability >= PREDICTION_THRESHOLD else 'normal'
        risk_signals = self.get_risk_signals(model_input, features)
        return {'prediction': prediction, 'scam_probability': scam_probability, 'risk_signals': risk_signals, 'error': None}
