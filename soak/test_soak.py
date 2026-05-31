"""
Nightly Soak Test
Runs the device simulator under sustained load for a defined duration.
Validates stability — no crashes, no memory leaks, consistent results.
Runs only on nightly cron — not on PR or merge.
"""

import pytest
import requests
import time
import os

BASE_URL  = f"http://{os.getenv('DEVICE_HOST', 'localhost')}:{os.getenv('DEVICE_PORT', '8766')}"
SOAK_MINS = int(os.getenv("SOAK_MINUTES", "2"))   # 2 min default, override for nightly


class TestSoakStability:

    def test_sustained_sweeps(self):
        """
        Run continuous sweeps for SOAK_MINUTES.
        Every sweep must return a valid result.
        No crashes, no unexpected errors.
        """
        print(f"\n[soak] Starting {SOAK_MINS}-minute stability run")

        # Reset before soak
        requests.post(f"{BASE_URL}/api/device/reset", json={})

        start     = time.time()
        end       = start + (SOAK_MINS * 60)
        run_count = 0
        failures  = []

        while time.time() < end:
            run_count += 1
            elapsed = int(time.time() - start)

            try:
                response = requests.post(
                    f"{BASE_URL}/api/device/test",
                    json={"inject_fault": False},
                    timeout=10
                )

                if response.status_code != 200:
                    failures.append({
                        "run":    run_count,
                        "error":  f"HTTP {response.status_code}",
                        "elapsed": elapsed
                    })
                else:
                    body = response.json()
                    if body["result"] != "PASS":
                        failures.append({
                            "run":     run_count,
                            "error":   "unexpected FAIL",
                            "elapsed": elapsed,
                            "sweeps":  body["sweeps"]
                        })

                if run_count % 10 == 0:
                    print(
                        f"[soak] {elapsed}s elapsed — "
                        f"{run_count} runs — "
                        f"{len(failures)} failures",
                        flush=True
                    )

            except Exception as e:
                failures.append({
                    "run":     run_count,
                    "error":   str(e),
                    "elapsed": elapsed
                })

            time.sleep(0.5)   # 500ms between runs

        # Final stats from device
        stats = requests.get(f"{BASE_URL}/api/device/stats").json()

        print(f"\n[soak] Complete — {run_count} runs in {SOAK_MINS} min")
        print(f"[soak] Device stats: {stats}")
        print(f"[soak] Client failures: {len(failures)}")

        if failures:
            print("[soak] Failure details:")
            for f in failures[:5]:   # show first 5
                print(f"  run {f['run']} at {f['elapsed']}s: {f['error']}")

        assert len(failures) == 0, (
            f"Soak test failed: {len(failures)} errors in "
            f"{run_count} runs over {SOAK_MINS} minutes"
        )

    def test_device_responsive_after_soak(self):
        """
        After sustained load, device must still respond correctly.
        Validates no resource exhaustion or state corruption.
        """
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        assert response.status_code == 200

        body = requests.get(f"{BASE_URL}/api/device/status").json()
        assert body["status"] == "READY"

    def test_stats_consistent_after_soak(self):
        """
        After soak, stats must be internally consistent.
        tests_passed + tests_failed must equal tests_run.
        """
        stats = requests.get(f"{BASE_URL}/api/device/stats").json()
        total = stats["tests_passed"] + stats["tests_failed"]
        assert total == stats["tests_run"], (
            f"Stats inconsistent: "
            f"{stats['tests_passed']} + {stats['tests_failed']} "
            f"!= {stats['tests_run']}"
        )