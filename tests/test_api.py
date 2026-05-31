"""
API Tests — validates device simulator REST endpoints.
Runs against the simulator on localhost:8766.
"""

import pytest
import requests
import os

BASE_URL = f"http://{os.getenv('DEVICE_HOST', 'localhost')}:{os.getenv('DEVICE_PORT', '8766')}"


class TestHealth:

    def test_health_returns_200(self):
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200

    def test_health_response_body(self):
        body = requests.get(f"{BASE_URL}/health").json()
        assert body["status"] == "ok"
        assert body["simulator"] is True


class TestDeviceStatus:

    def test_status_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/device/status")
        assert response.status_code == 200

    def test_status_is_ready(self):
        body = requests.get(f"{BASE_URL}/api/device/status").json()
        assert body["status"] == "READY"

    def test_status_has_firmware(self):
        body = requests.get(f"{BASE_URL}/api/device/status").json()
        assert "firmware" in body
        assert body["firmware"].startswith("fw-")

    def test_status_has_uptime(self):
        body = requests.get(f"{BASE_URL}/api/device/status").json()
        assert "uptime" in body
        assert isinstance(body["uptime"], int)

    def test_unknown_endpoint_returns_404(self):
        response = requests.get(f"{BASE_URL}/api/does-not-exist")
        assert response.status_code == 404


class TestRFSweep:

    def test_sweep_returns_200(self):
        response = requests.post(
            f"{BASE_URL}/api/device/test",
            json={}
        )
        assert response.status_code == 200

    def test_sweep_has_result_field(self):
        body = requests.post(f"{BASE_URL}/api/device/test", json={}).json()
        assert "result" in body
        assert body["result"] in ["PASS", "FAIL"]

    def test_sweep_has_three_passes(self):
        body = requests.post(f"{BASE_URL}/api/device/test", json={}).json()
        assert len(body["sweeps"]) == 3

    def test_sweep_deltas_below_threshold(self):
        body = requests.post(f"{BASE_URL}/api/device/test", json={}).json()
        for sweep in body["sweeps"]:
            assert sweep["delta"] < 0.010

    def test_sweep_has_firmware(self):
        body = requests.post(f"{BASE_URL}/api/device/test", json={}).json()
        assert "firmware" in body

    def test_fault_injection_returns_fail(self):
        body = requests.post(
            f"{BASE_URL}/api/device/test",
            json={"inject_fault": True}
        ).json()
        assert body["result"] == "FAIL"

    def test_fault_injection_has_high_delta(self):
        body = requests.post(
            f"{BASE_URL}/api/device/test",
            json={"inject_fault": True}
        ).json()
        high = [s for s in body["sweeps"] if s["delta"] >= 0.010]
        assert len(high) >= 1


class TestStats:

    def test_stats_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/device/stats")
        assert response.status_code == 200

    def test_stats_has_required_fields(self):
        body = requests.get(f"{BASE_URL}/api/device/stats").json()
        assert "tests_run" in body
        assert "tests_passed" in body
        assert "tests_failed" in body

    def test_stats_increment_after_sweep(self):
        before = requests.get(f"{BASE_URL}/api/device/stats").json()["tests_run"]
        requests.post(f"{BASE_URL}/api/device/test", json={})
        after = requests.get(f"{BASE_URL}/api/device/stats").json()["tests_run"]
        assert after == before + 1


class TestReset:

    def test_reset_returns_ack(self):
        body = requests.post(f"{BASE_URL}/api/device/reset", json={}).json()
        assert body["status"] == "RESET:ACK"

    def test_reset_clears_stats(self):
        # Run a test first to ensure counts > 0
        requests.post(f"{BASE_URL}/api/device/test", json={})
        # Reset
        requests.post(f"{BASE_URL}/api/device/reset", json={})
        # Check stats are zero
        body = requests.get(f"{BASE_URL}/api/device/stats").json()
        assert body["tests_run"] == 0