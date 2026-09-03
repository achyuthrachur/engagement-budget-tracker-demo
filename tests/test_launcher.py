from __future__ import annotations

import json
import socket
import unittest
from unittest.mock import patch

from app import find_available_port, find_running_tracker, open_browser_when_ready


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class LauncherTests(unittest.TestCase):
    @patch("app.urllib.request.urlopen")
    def test_running_tracker_is_reused(self, urlopen):
        urlopen.return_value = FakeResponse({
            "data": {"status": "ok", "app_version": "3.0.1", "schema_version": 3}
        })
        self.assertEqual(
            find_running_tracker((5002,)),
            "http://127.0.0.1:5002/")

    @patch("app.urllib.request.urlopen")
    def test_unrelated_local_service_is_not_reused(self, urlopen):
        urlopen.return_value = FakeResponse({"data": {"status": "ok"}})
        self.assertIsNone(find_running_tracker((5002,)))

    def test_port_selection_skips_an_occupied_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            port = occupied.getsockname()[1]
            self.assertIsNone(find_available_port((port,)))
        self.assertEqual(find_available_port((port,)), port)

    @patch("app.webbrowser.open")
    @patch("app.find_running_tracker", return_value="http://127.0.0.1:5001/dashboard")
    def test_browser_opens_after_health_is_ready(self, _find, browser_open):
        open_browser_when_ready("http://127.0.0.1:5001/dashboard", 5001)
        browser_open.assert_called_once_with("http://127.0.0.1:5001/dashboard")


if __name__ == "__main__":
    unittest.main()
