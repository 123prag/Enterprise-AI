"""Thin HTTP client wrapper shared by every Streamlit page.

The frontend talks to the FastAPI backend over HTTP (not by importing
app.* directly), matching the "FastAPI backend + Streamlit frontend"
split in the architecture -- the frontend and backend are meant to be
independently deployable.
"""

from __future__ import annotations

import os

import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


class APIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


def _handle(resp: requests.Response):
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise APIError(resp.status_code, detail)
    return resp.json()


def get(path: str, **kwargs):
    resp = requests.get(f"{API_BASE_URL}{path}", timeout=30, **kwargs)
    return _handle(resp)


def post(path: str, json: dict, **kwargs):
    resp = requests.post(f"{API_BASE_URL}{path}", json=json, timeout=60, **kwargs)
    return _handle(resp)
