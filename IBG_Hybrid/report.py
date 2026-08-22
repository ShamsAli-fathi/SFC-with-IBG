import pandas as pd
from math import isfinite
from numbers import Integral, Real

from IBG_Hybrid.csv_storage import HybridCsvError, append_metric_value


def _finite_metric(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not isfinite(float(value))
    ):
        raise HybridCsvError(f"{name} must be a finite number")
    return value


def SLA_v(embed_dict, replica_list):
    violation_count = 0
    for index, embeds in embed_dict.items():
        count_of_ones = sum(
            1 for index, rep in enumerate(embeds)
            if replica_list[(index + 1, rep)].state in (1, 2)
        )
        if count_of_ones > 0:
            violation_count += 1
    return violation_count


def csv_gen_SLA(
    violation_count,
    hash_value,
    filename='end_to_end_sla_violations.csv',
    *,
    announce=True,
):
    """
    Appends violation_count to a CSV file under a column named after hash_value.

    Args:
        violation_count: The numeric value to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'end_to_end_sla_violations.csv')
    """

    if (
        isinstance(violation_count, bool)
        or not isinstance(violation_count, Integral)
        or violation_count < 0
    ):
        raise HybridCsvError("SLA violation count must be a nonnegative integer")
    append_metric_value(filename, hash_value, int(violation_count))
    if announce:
        print(
            f"Added violation_count={violation_count} to column "
            f"'{hash_value}' in {filename}"
        )


def csv_gen_util(
    utility_value,
    hash_value,
    filename='aggregate_utility.csv',
    *,
    announce=True,
):
    """
    Appends end-to-end utility to a CSV file under a run column.

    Args:
        utility_value: The raw end-to-end utility value to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'aggregate_utility.csv')
    """

    value = _finite_metric(utility_value, "end-to-end utility")
    append_metric_value(filename, hash_value, float(value))
    if announce:
        print(f"Added util={utility_value} to column '{hash_value}' in {filename}")


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


def csv_gen_jain(
    jain_value,
    hash_value,
    filename='jain_index.csv',
    *,
    announce=True,
):
    """
    Appends Jain fairness to a CSV file under a run column.

    Args:
        jain_value: The Jain fairness value to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'jain_index.csv')
    """

    value = _finite_metric(jain_value, "Jain fairness")
    if not 0.0 <= float(value) <= 1.0:
        raise HybridCsvError("Jain fairness must be between zero and one")
    append_metric_value(filename, hash_value, float(value))
    if announce:
        print(f"Added jain={jain_value} to column '{hash_value}' in {filename}")


def csv_gen_time(
    elapsed_seconds,
    hash_value,
    filename='time.csv',
    *,
    announce=True,
):
    """
    Appends elapsed seconds to a CSV file under a run column.

    Args:
        elapsed_seconds: The nonnegative elapsed time to append
        hash_value: The hash string to use as column name
        filename: Name of the CSV file (default: 'time.csv')
    """

    value = _finite_metric(elapsed_seconds, "elapsed seconds")
    if float(value) < 0:
        raise HybridCsvError("elapsed seconds must be nonnegative")
    append_metric_value(filename, hash_value, float(value))
    if announce:
        print(f"Added time={elapsed_seconds} to column '{hash_value}' in {filename}")
