# RugPull Detector

A multichain ML-based system for rug-pull detection, trained on a combination of on-chain, code-based and off-chain signals, aimed to protect investors for fraud.

A user selects a blockchain (ETH, BSC, POLYGON or ARBI) and enters a token contract address. The system extracts features for this token, including on-chain (from blockchain explorers), price history, contract source code patterns and online presence, and passes them to a trained XGBoost model. It returns:
- a scam probability with a risk band (low / suspicious / high);
- top-3 risk signals (features that pushed the prediction towards 'scam') with their extracted values;
- all extracted features, so it is transparent what the prediction was based on.

The model is trained on a subset of features from the cleaned and enriched TM-RugPull dataset (971 projects across four blockchains). The classification threshold (0.58) was derived from cross-validated training predictions. Probabilities between 0.5 and 0.58 are shown as 'suspicious', since during validation missed rug-pulls fell into this range.

## How to run

Requires Python 3.9.

1. Install dependencies: 
```
pip install -r requirements.txt
```
2. Create an `.env` file in the project root with API keys:
   `ETHERSCAN_API_KEY`, `NODEREAL_API_KEY`, `MORALIS_API_KEY`, `COINGECKO_API_KEY`, `SERP_API_KEY`
3. Start the app: 
```
python app.py
```
4. Open http://localhost:5001 in a browser.

Scanning one token could take up to several minutes, since features are extracted live from external APIs with rate limits, and busy or old tokens require many paginated requests.

## Project structure
```
ML_RugPull_Detector
|- app.py
|- ui_module
|  |- webapp.py
|  |- templates
|     |- index.html
|- prediction_module
|  |- predictor.py
|  |- scan_token.py
|  |- models
|- feature_extraction_module
|  |- feature_extractor.py
|  |- helpers
|- tests
|- research
|  |- data
|  |  |- SOURCE CODE
|  |  |- top-200_token_snapshots
|  |  |- TM-RugPull_enriched_v.1.0.xlsx
|  |  |- TM-RugPull_original.xlsx
|  |  |- TM-RugPull_prepared_for_enrichment.xlsx
|  |- data analysis and model training
|  |- enrichment scripts
|  |- validation
|- xlsx_helpers
|- requirements.txt
|- requirements_dev.txt
|- pytest.ini
|- README.md
```

## Tests

Tests are designed to be fully offline (all external services, the model and pipeline stages are mocked), so no API keys are needed.
To run tests, use: 
```
pytest
```

## Validation

`research/validation/validation.py` runs end-to-end system validation on 28 tokens that were not included into the training dataset: 9 documented rug pulls and 19 legitimate tokens of different chains, sizes, ages and kinds. 
To run it from the project root:
```
python -m research.validation.validation
```

Note that each token costs up to 3 SerpApi searches and several minutes of API calls. Results are saved as a .csv file and as JSON snapshots of extracted features.

## Guide to files and directories

- `app.py`: a single entry point, starts the application.
- `ui_module`: a presentation layer.
- `prediction_module`: a part of an app that makes predictions using a pre-trained model:
   - `predictor.py` loads the trained model with pre-processors and makes predictions;
   - `scan_token.py` wires feature extraction and prediction together;
   - `models` directory contains the trained XGBoost model and pre-processing artifacts.
- `feature_extraction_module`: a part of an app that extract features for a queried token live. Features extracted by this module match features that were used to train the model:
  - `feature_extractor.py` performs extraction of all features for one token;
  - `helpers` directory contains extraction helpers dedicated to different features and sources.
- `tests`: 194 offline tests + `mock_env.py` (contains mocked structures) and `conftest.py` (contains shared fixtures).
- `research`: everything used to analyse data, train and tune the model; is not required to run the app:
  - `data`: dataset versions in .xlsx format; 
  - `data/SOURCE CODE` contains contract source code for all projects from the dataset in .txt files (named in line with original dataset row numbers);
  - `data/top-200_token_snapshots` contains temporal snapshots of top-200 tokens that were used to enrich the dataset with 'token_name_similarity' feature;
  - `data analysis and model training` contains Jupyter notebooks: 'TM-RugPull initial analysis' (analysis of the original dataset, experiments with pre-processing and visualisation) and 'Experimentation pipeline and model training' (the pre-processing pipeline, candidate models comparison and export of the final model);
  - `enrichment scripts`: scripts that enriched the dataset with new features (holder counts after deployment, contract code patterns, project period, name similarity to top-200 tokens);
  - `validation`: a validation script and saved results of validation run;
- `xlsx_helpers`: shared helpers for reading and writing dataset .xlsx files.
- `requirements.txt`: versions required to run the app (kept the same as used for model training).
- `requirements_dev.txt`: full environment for the notebooks and tests.
- `pytest.ini`: pytest configuration (tests are run from the project root).

