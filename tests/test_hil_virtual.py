"""
HIL Service Virtualisation Tests
Simulates hardware-in-the-loop testing without physical hardware.
The device simulator acts as the virtual device.
"""

import pytest
import requests
import time
import os

BASE_URL = f"http://{os.getenv('DEVICE_HOST', 'localhost')}:{os.getenv('DEVICE_PORT', '8766')}"


class TestDeviceBootSequence:
    """Simulates device power-on and boot validation."""

    def test_device_responds_after_boot(self):
        """Device must respond to health check — simulates boot check."""
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        assert response.status_code == 200

    def test_device_status_ready_after_boot(self):
        """Device must report READY — simulates STATUS:READY serial check."""
        body = requests.get(f"{BASE_URL}/api/device/status").json()
        assert body["status"] == "READY"

    def test_firmware_version_matches_expected(self):
        """Firmware version must match expected build."""
        expected = os.getenv("EXPECTED_FIRMWARE", "fw-2.4.1-release")
        body = requests.get(f"{BASE_URL}/api/device/status").json()
        assert body["firmware"] == expected, (
            f"Firmware mismatch: got {body['firmware']}, expected {expected}"
        )


class TestRFSweepValidation:
    """Simulates RF sweep test execution and result validation."""

    def test_single_sweep_completes(self):
        """A single RF sweep must complete and return a result."""
        response = requests.post(
            f"{BASE_URL}/api/device/test",
            json={},
            timeout=10
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"] in ["PASS", "FAIL"]

    def test_sweep_has_correct_structure(self):
        """Sweep response must have result, sweeps array, and firmware."""
        body = requests.post(
            f"{BASE_URL}/api/device/test", json={}
        ).json()
        assert "result"   in body
        assert "sweeps"   in body
        assert "firmware" in body
        assert len(body["sweeps"]) == 3

    def test_normal_sweep_passes(self):
        """Normal sweep without fault injection must return PASS."""
        body = requests.post(
            f"{BASE_URL}/api/device/test",
            json={"inject_fault": False}
        ).json()
        assert body["result"] == "PASS"
        for sweep in body["sweeps"]:
            assert sweep["delta"] < 0.010

    def test_faulty_component_detected(self):
        """
        Fault-injected sweep must return FAIL.
        Simulates Anvil detecting a counterfeit component.
        """
        body = requests.post(
            f"{BASE_URL}/api/device/test",
            json={"inject_fault": True}
        ).json()
        assert body["result"] == "FAIL"
        high_deltas = [s for s in body["sweeps"] if s["delta"] >= 0.010]
        assert len(high_deltas) >= 1, "Expected at least one failing sweep"

    def test_multiple_sweeps_consistent(self):
        """Run 3 consecutive sweeps — all must pass without fault injection."""
        for i in range(3):
            body = requests.post(
                f"{BASE_URL}/api/device/test",
                json={"inject_fault": False}
            ).json()
            assert body["result"] == "PASS", f"Sweep {i+1} failed unexpectedly"


class TestDeviceStateManagement:
    """Simulates device state tracking — equivalent to HIL log capture."""

    def test_stats_tracked_correctly(self):
        """Stats must increment after each test run."""
        # Reset to known state
        requests.post(f"{BASE_URL}/api/device/reset", json={})

        # Run two tests
        requests.post(f"{BASE_URL}/api/device/test", json={})
        requests.post(f"{BASE_URL}/api/device/test", json={})

        stats = requests.get(f"{BASE_URL}/api/device/stats").json()
        assert stats["tests_run"] == 2

    def test_pass_count_increments(self):
        """Pass count must increment for successful sweeps."""
        requests.post(f"{BASE_URL}/api/device/reset", json={})
        requests.post(
            f"{BASE_URL}/api/device/test",
            json={"inject_fault": False}
        )
        stats = requests.get(f"{BASE_URL}/api/device/stats").json()
        assert stats["tests_passed"] == 1
        assert stats["tests_failed"] == 0

    def test_fail_count_increments(self):
        """Fail count must increment for failed sweeps."""
        requests.post(f"{BASE_URL}/api/device/reset", json={})
        requests.post(
            f"{BASE_URL}/api/device/test",
            json={"inject_fault": True}
        )
        stats = requests.get(f"{BASE_URL}/api/device/stats").json()
        assert stats["tests_failed"] == 1
        assert stats["tests_passed"] == 0

    def test_reset_clears_all_state(self):
        """Reset must clear all counters — simulates power cycle."""
        # Accumulate some state
        requests.post(f"{BASE_URL}/api/device/test", json={})
        requests.post(f"{BASE_URL}/api/device/test", json={})

        # Reset
        body = requests.post(
            f"{BASE_URL}/api/device/reset", json={}
        ).json()
        assert body["status"] == "RESET:ACK"

        # Verify cleared
        stats = requests.get(f"{BASE_URL}/api/device/stats").json()
        assert stats["tests_run"]    == 0
        assert stats["tests_passed"] == 0
        assert stats["tests_failed"] == 0


class TestErrorHandling:
    """Simulates error conditions the pipeline must handle."""

    def test_invalid_endpoint_returns_404(self):
        """Unknown endpoints must return 404 — not crash."""
        response = requests.get(f"{BASE_URL}/api/nonexistent")
        assert response.status_code == 404

    def test_empty_post_body_handled(self):
        """Empty POST body must be handled gracefully."""
        response = requests.post(
            f"{BASE_URL}/api/device/test",
            json=None,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200