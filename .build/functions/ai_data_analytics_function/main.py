"""Catalyst Advanced I/O entry point for the AI Data Analytics API."""

from flask import Request

from api.router import dispatch
from common.core import AuthenticationRequired, json_response


def handler(request: Request):
    try:
        return dispatch(request)
    except AuthenticationRequired as exc:
        return json_response(
            {
                "error": {
                    "code": "AUTHENTICATION_REQUIRED",
                    "message": str(exc),
                }
            },
            401,
        )
