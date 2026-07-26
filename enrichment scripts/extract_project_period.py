# Compute project period for each token from the dataset using project start date and project end date
# Since project's start and end dates are not informative for any model by themselves, it was decided to use them
# to calculate project period, which could have predictive power to detect rug-pulls, since projects that live longer
# are less likely to be fraudulent.

import pandas as pd
