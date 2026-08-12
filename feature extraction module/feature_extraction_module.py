# Extract features from any queried token on Eth, BSC, Arbitrum or Polygon using token contract address
# Is used for feature extraction module of the application. Once extracted, features are submitted to the prediction module,
# where the developed model consume them to make a prediction


# Features to extract (based on features list used by the model from the prediction module
# ['MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)', 'the number of Transactions', 'Token concentration ratio per holder',
# 'Google results for project website (first day)', 'Google results for project x profile (first days)',
# 'Google results for project x profile (duration/2)', 'project period (days)', 'Holders_12h',
# 'Holders_24h', 'has_contract_swap_patterns', 'has_owner_guard', 'Blockchain Type_POS', 'Blockchain Type_POSA']

# Return type: float64


# TODO: a function for each feature + feeding features into the model