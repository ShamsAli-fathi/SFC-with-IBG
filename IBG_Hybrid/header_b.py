def update_b(last_embed, number_of_replicas, replica_list):
    replica_congestion = {}
    for value_list in last_embed.values():
        for t in value_list:
            # Update the count for each tuple
            replica_congestion[t] = replica_congestion.get(t, 0) + 1

    local_belief = {k: [] for k in replica_congestion}
    last_embed_flattened = [tup for sublist in last_embed.values() for tup in sublist]

    for rep in last_embed_flattened:
        signal, like = replica_list[rep].tasting(replica_congestion[rep])
        result = replica_list[rep].local_update(like, signal)
        local_belief[rep].append(result)

    for rep, beliefs in local_belief.items():
        if local_belief[rep]:
            replica_list[rep].aggregation(local_belief[rep])


def SLA_v_b(embed_dict, replica_list):
    violation_count = 0

    last_embed_flattened = [tup for sublist in embed_dict.values() for tup in sublist]

    for rep in last_embed_flattened:
        # Check if state is 1 or 2
        if replica_list[rep].state in [1, 2]:
            violation_count += 1
    return violation_count

def SLA_v_b_v2(per_flow_latency, threshold=15):
    violation_count = 0
    for f, latency in per_flow_latency.items():
        if latency > threshold:
            violation_count += 1
    return violation_count
