# RugPull Detector

A multichain ML-based system for rug-pull detection, trained on a combination of on-chain, code-based and off-chain signals, aimed to protect investors from fraud.

A user selects a blockchain (ETH, BSC, POLYGON or ARBI) and enters a token contract address. The system extracts features for this token, including on-chain (from blockchain explorers), price history, source code patterns and Google search counts, and passes them to a trained XGBoost model. It returns:
- a scam probability with a risk band (low / suspicious / high);
- top-3 risk signals (features that contributed most to the 'scam' prediction) with extracted values;
- all extracted features, to make an input for the model transparent.

The model is trained on a subset of features from the cleaned and enriched TM-RugPull dataset (971 projects across four blockchains). The classification threshold (0.58) was determined by cross-validated training predictions. Probabilities between 0.5 and 0.58 fall into 'suspicious' band.

## How to run

Requires Python 3.9.

1. Install dependencies: 
```
pip install -r requirements.txt
```
2. Create an `.env` file in the project root with API keys:
   `ETHERSCAN_API_KEY`, `NODEREAL_API_KEY`, `MORALIS_API_KEY`, `COINGECKO_API_KEY`, `SERP_API_KEY`. 
API keys used for the Project are avaliable in the Project's report Appendix.
3. Start the app: 
```
python app.py
```
4. Open http://localhost:5001 in a browser.

Scanning one token could take up to several minutes, since features are extracted live from external sources with rate limits, so busy or old tokens require many paginated requests.

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

All 197 automated tests are offline, so no API keys are required.
To run tests, use: 
```
pytest
```

## Validation

`research/validation/validation.py` runs system validation on 28 tokens that were not included into the dataset: 9 documented rug-pulls and 19 legitimate tokens of different chains, sizes, ages and kinds. 

To run from the project root:
```
python -m research.validation.validation
```

Note that each token costs up to 3 SerpAPI searches and several minutes of processing. Results are saved as a .csv file and JSON snapshots of extracted features.

## Guide to files and directories

- `app.py`: runs the application.
- `ui_module`: a presentation layer.
- `prediction_module`: makes predictions using a pre-trained model:
   - `predictor.py` loads the trained model with pre-processors and makes predictions;
   - `scan_token.py` wires feature extraction and prediction together;
   - `models` directory contains the trained XGBoost model and pre-processing pipeline.
- `feature_extraction_module`: extracts features for a queried token. Features extracted by this module match features that were used to train the model:
  - `feature_extractor.py` performs extraction of all features for one token;
  - `helpers` directory contains extraction helpers dedicated to different features and sources.
- `tests`: 197 offline tests + `mock_env.py` (contains mocked structures) and `conftest.py` (contains shared fixtures).
- `research`: everything used to analyse data, train and tune the model; is not required to run the app:
  - `data`: dataset versions in .xlsx format; 
  - `data/SOURCE CODE` contains contract source code for all projects from the dataset in .txt files (named in line with original dataset row numbers);
  - `data/top-200_token_snapshots` contains temporal snapshots of top-200 tokens that were used to enrich the dataset with 'token_name_similarity' feature;
  - `data analysis and model training` contains Jupyter notebooks: 'TM-RugPull initial analysis' (analysis of the original dataset, experiments with pre-processing and visualisation) and 'Experimentation pipeline and model training' (pre-processing pipeline, models comparison and export of the final model);
  - `enrichment scripts`: scripts used for the dataset enrichment with new features;
  - `validation`: a validation script + saved results of a performed validation run;
- `xlsx_helpers`: helper functions for reading and writing .xlsx files.
- `requirements.txt`: versions required to run the app (same as used model training).
- `requirements_dev.txt`: full environment for reproduction of notebooks and tests.
- `pytest.ini`: pytest configuration (tests are run from the project root).

