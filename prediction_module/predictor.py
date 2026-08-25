import joblib

# Paths to the model and pre-processor
MODEL_PATH = 'models/xgboost_model.json'
PREPROCESSING_PATH = 'models/preprocessing.joblib'

# Probability threshold to convert scam probability into class
# 0.6 is chosen to ensure the model does not give predictions which could be as good as random results
PREDICTION_THRESHOLD = 0.6


# Take a dictionary of extracted features and return scam probability with a class label
class Predictor:
    # Model and pre-processors are loaded once and reused for all predictions
    def __init__(self, model_path=MODEL_PATH, preprocessing_path=PREPROCESSING_PATH, xgb=None):
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


    # TODO
    def prepare_model_input(self, features):
        return


    # Make a prediction based on extracted features
    # Return 'prediction' ('scam' or 'normal'), 'scam_probability' (float between 0 and 1) and 'error' (if any)
    def predict(self, features):
        if not features:
            return {'prediction': None, 'scam_probability': None, 'error': 'No features to predict on'}
        model_input = self.prepare_model_input(features)
        if model_input is None:
            return {'prediction': None, 'scam_probability': None, 'error': 'Features could not be pre-processed'}
        scam_probability = float(self.model.predict_proba(model_input.to_numpy())[0, self.scam_class_index])
        prediction = 'scam' if scam_probability >= PREDICTION_THRESHOLD else 'normal'
        return {'prediction': prediction, 'scam_probability': scam_probability, 'error': None}
