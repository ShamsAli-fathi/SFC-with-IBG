import pandas as pd
import numpy as np
import os


def SLA_v(end_to_end_latency_ms_per_flow, threshold_ms):
    """Count flows whose observed end-to-end latency exceeds the SLA."""
    if threshold_ms <= 0:
        raise ValueError("SLA latency threshold must be positive")
    return sum(
        latency_ms > threshold_ms
        for latency_ms in end_to_end_latency_ms_per_flow.values()
    )


def csv_gen_SLA(violation_count, hash_value, filename='sla_violations.csv'):
    """
    Appends violation_count to a CSV file under a column named after hash_value.

    Args:
        violation_count: The numeric value to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'sla_violations.csv')
    """

    # Check if file exists
    if os.path.exists(filename):
        # Read existing CSV
        df = pd.read_csv(filename)

        # Check if column with this hash exists
        if hash_value in df.columns:
            # Find the first empty (NaN) row in this column
            empty_idx = df[hash_value].isna().idxmax() if df[hash_value].isna().any() else len(df)

            # If no empty rows exist, add a new row
            if empty_idx == len(df):
                df.loc[empty_idx] = None

            # Set the value in the specific column at the empty index
            df.loc[empty_idx, hash_value] = violation_count
        else:
            # Add new column with the violation_count in the first row
            df[hash_value] = None
            df.loc[0, hash_value] = violation_count
    else:
        # Create new DataFrame with the hash as column name
        df = pd.DataFrame({hash_value: [violation_count]})

    # Save back to CSV
    df.to_csv(filename, index=False)
    print(f"Added violation_count={violation_count} to column '{hash_value}' in {filename}")


def csv_gen_util(violation_count, hash_value, filename='aggregate_utility.csv'):
    """
    Appends violation_count to a CSV file under a column named after hash_value.

    Args:
        violation_count: The numeric value to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'sla_violations.csv')
    """

    # Check if file exists
    if os.path.exists(filename):
        # Read existing CSV
        df = pd.read_csv(filename)

        # Check if column with this hash exists
        if hash_value in df.columns:
            # Find the first empty (NaN) row in this column
            empty_idx = df[hash_value].isna().idxmax() if df[hash_value].isna().any() else len(df)

            # If no empty rows exist, add a new row
            if empty_idx == len(df):
                df.loc[empty_idx] = None

            # Set the value in the specific column at the empty index
            df.loc[empty_idx, hash_value] = violation_count
        else:
            # Add new column with the violation_count in the first row
            df[hash_value] = None
            df.loc[0, hash_value] = violation_count
    else:
        # Create new DataFrame with the hash as column name
        df = pd.DataFrame({hash_value: [violation_count]})

    # Save back to CSV
    df.to_csv(filename, index=False)
    print(f"Added util={violation_count} to column '{hash_value}' in {filename}")


def plot_sla_violations(filename):
    """
    Reads the SLA violations CSV from the current directory,
    averages each row across all columns, and plots it per iteration.
    """
    import matplotlib.pyplot as plt

    # Load data
    df = pd.read_csv(filename)

    # Compute the mean of each row
    df["Average"] = df.mean(axis=1)

    # Plot
    plt.figure(figsize=(10, 5))
    plt.plot(df.index + 1, df["Average"], marker="o")
    plt.xlabel("Iteration")
    plt.ylabel("SLA Violation (Average)")
    plt.title("Average SLA Violation per Iteration")
    plt.xticks(df.index + 1)
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def csv_gen_jain(violation_count, hash_value, filename='jain_index.csv'):
    """
    Appends violation_count to a CSV file under a column named after hash_value.

    Args:
        violation_count: The numeric value to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'sla_violations.csv')
    """

    # Check if file exists
    if os.path.exists(filename):
        # Read existing CSV
        df = pd.read_csv(filename)

        # Check if column with this hash exists
        if hash_value in df.columns:
            # Find the first empty (NaN) row in this column
            empty_idx = df[hash_value].isna().idxmax() if df[hash_value].isna().any() else len(df)

            # If no empty rows exist, add a new row
            if empty_idx == len(df):
                df.loc[empty_idx] = None

            # Set the value in the specific column at the empty index
            df.loc[empty_idx, hash_value] = violation_count
        else:
            # Add new column with the violation_count in the first row
            df[hash_value] = None
            df.loc[0, hash_value] = violation_count
    else:
        # Create new DataFrame with the hash as column name
        df = pd.DataFrame({hash_value: [violation_count]})

    # Save back to CSV
    df.to_csv(filename, index=False)
    print(f"Added jain={violation_count} to column '{hash_value}' in {filename}")


def csv_gen_time(violation_count, hash_value, filename='time.csv'):
    """
    Appends violation_count to a CSV file under a column named after hash_value.

    Args:
        violation_count: The numeric value to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'sla_violations.csv')
    """

    # Check if file exists
    if os.path.exists(filename):
        # Read existing CSV
        df = pd.read_csv(filename)

        # Check if column with this hash exists
        if hash_value in df.columns:
            # Find the first empty (NaN) row in this column
            empty_idx = df[hash_value].isna().idxmax() if df[hash_value].isna().any() else len(df)

            # If no empty rows exist, add a new row
            if empty_idx == len(df):
                df.loc[empty_idx] = None

            # Set the value in the specific column at the empty index
            df.loc[empty_idx, hash_value] = violation_count
        else:
            # Add new column with the violation_count in the first row
            df[hash_value] = None
            df.loc[0, hash_value] = violation_count
    else:
        # Create new DataFrame with the hash as column name
        df = pd.DataFrame({hash_value: [violation_count]})

    # Save back to CSV
    df.to_csv(filename, index=False)
    print(f"Added time={violation_count} to column '{hash_value}' in {filename}")
