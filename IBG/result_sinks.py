from pathlib import Path

from header import create_belief_csv
from report import csv_gen_SLA, csv_gen_jain, csv_gen_time, csv_gen_util


class CsvResultSink:
    """Persist slot metrics using the reference CSV reporting functions."""

    def __init__(self, hash_value, replica_list, output_dir="."):
        self.hash_value = hash_value
        self.replica_list = replica_list
        self.output_dir = Path(output_dir)

    def record_slot(self, result):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        csv_gen_time(
            result.elapsed_seconds,
            self.hash_value,
            filename=self.output_dir / "time.csv",
        )
        csv_gen_SLA(
            result.sla_violations,
            self.hash_value,
            filename=self.output_dir / "sla_violations.csv",
        )
        csv_gen_util(
            result.aggregate_utility_total,
            self.hash_value,
            filename=self.output_dir / "aggregate_utility.csv",
        )
        csv_gen_jain(
            result.jain_fairness,
            self.hash_value,
            filename=self.output_dir / "jain_index.csv",
        )
        create_belief_csv(
            self.replica_list,
            filename=self.output_dir / "replica_results.csv",
        )
