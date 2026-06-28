import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import warnings
import os

warnings.filterwarnings('ignore')

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(script_dir, 'sla_violations.csv')

# Read the CSV file
print(f"Reading CSV from: {csv_path}")
df = pd.read_csv(csv_path)

print("Original DataFrame shape:", df.shape)
print("\nMissing values per column:")
print(df.isnull().sum())


def fill_column_with_trend(column):
    """
    Fill missing values in a column by fitting a regression model
    on the existing values and predicting the missing ones.
    """
    # Get indices of non-null and null values
    non_null_idx = column[column.notna()].index.values
    null_idx = column[column.isna()].index.values

    # If no missing values, return as is
    if len(null_idx) == 0:
        return column

    # If not enough data points for regression (need at least 2), use forward fill
    if len(non_null_idx) < 2:
        return column.fillna(method='ffill').fillna(0)

    # Prepare data for regression
    X_train = non_null_idx.reshape(-1, 1)
    y_train = column[non_null_idx].values

    # Fit linear regression model
    model = LinearRegression()
    model.fit(X_train, y_train)

    # Predict missing values
    X_predict = null_idx.reshape(-1, 1)
    predictions = model.predict(X_predict)

    # Ensure predictions are non-negative (can't have negative violations)
    predictions = np.maximum(predictions, 0)

    # Round to integers
    predictions = np.round(predictions).astype(int)

    # Fill the missing values
    filled_column = column.copy()
    filled_column.iloc[null_idx] = predictions

    return filled_column


# Apply the trend filling to each column
df_filled = df.copy()
for col in df_filled.columns:
    df_filled[col] = fill_column_with_trend(df_filled[col])

print("\n" + "=" * 80)
print("FILLED DataFrame:")
print("=" * 80)
print(df_filled)

print("\n" + "=" * 80)
print("Missing values after filling:")
print(df_filled.isnull().sum())

# Save the filled dataframe
output_path = os.path.join(script_dir, 'sla_violations_filled.csv')
df_filled.to_csv(output_path, index=False)
print(f"\nFilled CSV saved as: {output_path}")

# Show some statistics about the filling
print("\n" + "=" * 80)
print("Filling Statistics:")
print("=" * 80)
for col in df.columns:
    original_nulls = df[col].isnull().sum()
    if original_nulls > 0:
        print(f"\nColumn: {col}")
        print(f"  Missing values filled: {original_nulls}")
        print(f"  Original last valid value: {df[col].dropna().iloc[-1]}")
        print(f"  Filled last value: {df_filled[col].iloc[-1]}")
        print(f"  Trend: {'Declining' if df_filled[col].iloc[-1] < df[col].dropna().iloc[0] else 'Stable/Increasing'}")