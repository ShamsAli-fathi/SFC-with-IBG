from collections import defaultdict


def apply_observations(observations, replica_list):
    """Apply collected observations with the existing local/aggregate rules."""
    local_beliefs = defaultdict(list)

    for observation in observations:
        replica = replica_list[(observation.stage, observation.replica_id)]
        local_beliefs[(observation.stage, observation.replica_id)].append(
            replica.local_update(observation.likelihood, observation.signal)
        )

    for replica_key, beliefs in local_beliefs.items():
        replica_list[replica_key].aggregation(beliefs)
