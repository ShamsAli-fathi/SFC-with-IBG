import sys
import time

import httpx


BASE_URL = "http://127.0.0.1:18081"


def wait_until_ready(timeout_seconds=90):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{BASE_URL}/health", timeout=2)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("flow generator did not become ready")


def main():
    wait_until_ready()
    routes = []
    for flow_id in (1, 2, 3):
        routes.append(
            {
                "flow_id": flow_id,
                "hops": [
                    {
                        "stage": stage,
                        "replica_id": 1,
                        "url": f"http://stage-{stage}-0:8080",
                    }
                    for stage in (1, 2, 3)
                ],
            }
        )

    response = httpx.post(
        f"{BASE_URL}/run-slot",
        json={"slot_id": 1, "routes": routes},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    assert result["slot_id"] == 1
    assert len(result["flows"]) == 3
    assert all(len(flow["hops"]) == 3 for flow in result["flows"])
    assert all(
        [hop["stage"] for hop in flow["hops"]] == [1, 2, 3]
        for flow in result["flows"]
    )
    stage_one_concurrency = sorted(
        flow["hops"][0]["concurrency"] for flow in result["flows"]
    )
    assert stage_one_concurrency == [1, 2, 3]
    print(
        "phase4 smoke: 3 flows x 3 hops completed; "
        f"stage-1 concurrency={stage_one_concurrency}; "
        f"elapsed_ms={result['elapsed_ms']:.3f}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"phase4 smoke failed: {error}", file=sys.stderr)
        raise
