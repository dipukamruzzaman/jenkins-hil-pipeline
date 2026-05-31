"""
UI Tests — validates device simulator via Playwright browser.
Tests the REST API through a real browser context with network interception.
This simulates what a dashboard UI would do when talking to the device.
"""

import pytest
import json
from playwright.sync_api import sync_playwright
import os

BASE_URL = f"http://{os.getenv('DEVICE_HOST', 'localhost')}:{os.getenv('DEVICE_PORT', '8766')}"


@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        browser.close()


@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    yield page
    page.close()


class TestHealthViaUI:

    def test_health_endpoint_reachable(self, page):
        """Browser can reach the health endpoint."""
        response = page.request.get(f"{BASE_URL}/health")
        assert response.status == 200

    def test_health_returns_json(self, page):
        """Health response is valid JSON with correct fields."""
        response = page.request.get(f"{BASE_URL}/health")
        body = response.json()
        assert body["status"] == "ok"
        assert body["simulator"] is True


class TestNetworkInterception:
    """
    Playwright network interception tests.
    Browser navigates to the simulator HTML page first —
    establishing a real origin — then fetch() calls work correctly.
    This is the capability Selenium cannot do without a proxy tool.
    """

    def test_intercept_status_request(self, page):
        """Intercept device status request from browser context."""
        intercepted = []

        def handle_request(request):
            if "/api/device/status" in request.url:
                intercepted.append({
                    "url":    request.url,
                    "method": request.method,
                })

        page.on("request", handle_request)
        page.goto(f"{BASE_URL}/")
        page.evaluate("fetch('/api/device/status')")
        page.wait_for_timeout(1000)

        assert len(intercepted) >= 1
        assert intercepted[-1]["method"] == "GET"
        assert "/api/device/status" in intercepted[-1]["url"]

    def test_intercept_sweep_response(self, page):
        """Intercept sweep response from browser context."""
        responses = []

        def handle_response(response):
            if "/api/device/test" in response.url:
                responses.append({
                    "status": response.status,
                    "body":   response.json(),
                })

        page.on("response", handle_response)
        page.goto(f"{BASE_URL}/")
        page.evaluate("""
            fetch('/api/device/test', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            })
        """)
        page.wait_for_timeout(2000)

        assert len(responses) == 1
        assert responses[0]["status"] == 200
        assert responses[0]["body"]["result"] in ["PASS", "FAIL"]
        assert len(responses[0]["body"]["sweeps"]) == 3

    def test_intercept_fault_injection(self, page):
        """Intercept fault injection — validate payload and FAIL response."""
        requests_captured  = []
        responses_captured = []

        def handle_request(request):
            if "/api/device/test" in request.url:
                requests_captured.append({
                    "post_data": request.post_data,
                })

        def handle_response(response):
            if "/api/device/test" in response.url:
                responses_captured.append(response.json())

        page.on("request",  handle_request)
        page.on("response", handle_response)
        page.goto(f"{BASE_URL}/")
        page.evaluate("""
            fetch('/api/device/test', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({inject_fault: true})
            })
        """)
        page.wait_for_timeout(2000)

        assert len(requests_captured) == 1
        payload = json.loads(requests_captured[0]["post_data"])
        assert payload["inject_fault"] is True

        assert len(responses_captured) == 1
        assert responses_captured[0]["result"] == "FAIL"

    def test_mock_cloud_503_response(self, page):
        """
        Inject a 503 response using page.route.
        Route intercepts browser fetch() calls from a real page origin.
        This is impossible with Selenium without a proxy tool.
        """
        page.route(
            "**/api/device/status",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"error": "service unavailable"})
            )
        )

        page.goto(f"{BASE_URL}/")
        result = page.evaluate("""
            async () => {
                const resp = await fetch('/api/device/status');
                const body = await resp.json();
                return { status: resp.status, body: body };
            }
        """)

        assert result["status"] == 503
        assert "error" in result["body"]
        page.unroute("**/api/device/status")

    def test_validate_content_type_header(self, page):
        """Validate Content-Type header via browser fetch."""
        page.goto(f"{BASE_URL}/")
        result = page.evaluate("""
            async () => {
                const resp = await fetch('/health');
                return resp.headers.get('content-type');
            }
        """)
        assert result is not None
        assert "application/json" in result