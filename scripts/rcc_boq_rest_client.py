#!/usr/bin/env python3
"""Local command-line client for the token-protected RCC BOQ REST Gateway."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://127.0.0.1:48885"
TOKEN_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "RCC_BOQ",
    "rest_token.txt",
)


def read_token(path=TOKEN_PATH):
    with open(path, "r", encoding="ascii") as token_file:
        token = token_file.read().strip()
    if len(token) != 64:
        raise ValueError("REST token file is invalid")
    return token


def endpoint_path(command, element_id=None):
    if command in ("status", "document", "selection"):
        return "/rcc-boq/" + command
    if command in ("element", "rebar") and element_id is not None:
        return "/rcc-boq/{0}/{1}".format(command + "s" if command == "element" else command, element_id)
    if command == "set-parameter" and element_id is not None:
        return "/rcc-boq/elements/{0}/parameter".format(element_id)
    raise ValueError("An element ID is required")


def call_api(path, base_url=DEFAULT_BASE_URL, token_path=TOKEN_PATH, timeout=30, body=None):
    token = read_token(token_path)
    data = None
    headers = {"Authorization": "Bearer " + token}
    method = "GET"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers=headers,
        data=data,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body)
        except ValueError:
            body = {"ok": False, "error": body}
        return error.code, body


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("status", "document", "selection", "element", "rebar", "set-parameter"),
    )
    parser.add_argument("element_id", nargs="?", type=int)
    parser.add_argument("--parameter-name")
    parser.add_argument("--value")
    parser.add_argument("--expected-current-value")
    parser.add_argument("--request-id")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the edit; without this flag set-parameter is a dry-run preview.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token-file", default=TOKEN_PATH)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        path = endpoint_path(args.command, args.element_id)
        body = None
        if args.command == "set-parameter":
            if not args.parameter_name or args.value is None:
                raise ValueError("--parameter-name and --value are required")
            body = {
                "parameterName": args.parameter_name,
                "value": args.value,
                "expectedCurrentValue": args.expected_current_value,
                "dryRun": not args.apply,
                "requestId": args.request_id,
            }
        status, payload = call_api(
            path,
            args.base_url,
            args.token_file,
            body=body,
        )
    except (OSError, ValueError, urllib.error.URLError) as error:
        print("RCC BOQ REST client error: {0}".format(error), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
