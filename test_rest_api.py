"""Plain-Python regression tests for the secure RCC BOQ REST contract."""

import json
import os
import sys
import tempfile
import importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(ROOT, "Nudge.extension", "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import rest_api
import agent_export_job

CLIENT_PATH = os.path.join(ROOT, "scripts", "rcc_boq_rest_client.py")
CLIENT_SPEC = importlib.util.spec_from_file_location("rcc_boq_rest_client", CLIENT_PATH)
rest_client = importlib.util.module_from_spec(CLIENT_SPEC)
CLIENT_SPEC.loader.exec_module(rest_client)


class FakeId:
    def __init__(self, value):
        self.Value = value


class FakeDefinition:
    def __init__(self, name):
        self.Name = name


class FakeParameter:
    HasValue = True
    StorageType = "String"

    def __init__(self, name, value):
        self.Definition = FakeDefinition(name)
        self._value = value

    def AsString(self):
        return self._value

    def AsValueString(self):
        return self._value


class FakeVaryingParameter(FakeParameter):
    HasValue = False

    def AsString(self):
        return None


class FakeCategory:
    def __init__(self, name):
        self.Name = name


class FakeParameters(list):
    @property
    def Size(self):
        return len(self)


class FakeElement:
    def __init__(self, value, category="Structural Rebar", parameters=None):
        self.Id = FakeId(value)
        self.UniqueId = "uid-{0}".format(value)
        self.Name = "Element {0}".format(value)
        self.Category = FakeCategory(category)
        self.Parameters = FakeParameters(parameters or [])

    def GetTypeId(self):
        return FakeId(-1)

    def GetHostId(self):
        return FakeId(42)


class FakeDocument:
    Title = "Safe model title"
    IsFamilyDocument = False

    def __init__(self, elements):
        self._elements = {item.Id.Value: item for item in elements}

    def GetElement(self, element_id):
        value = rest_api.element_id_value(element_id)
        return self._elements.get(value)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    check(rest_api.constant_time_equal("abc", "abc"), "equal token rejected")
    check(not rest_api.constant_time_equal("abc", "abd"), "wrong token accepted")
    check(not rest_api.constant_time_equal("abc", "abc0"), "wrong length accepted")
    check(rest_api.request_is_authorized({"token": "secret"}, "secret"), "JSON token rejected")
    check(not rest_api.request_is_authorized("secret", "secret"), "non-object body accepted")
    check(
        rest_api.parameter_value(FakeVaryingParameter("A", "<varies>")) == "<varies>",
        "varying display value lost when HasValue is false",
    )

    startup_path = os.path.join(ROOT, "Nudge.extension", "startup.disabled.py")
    with open(startup_path, "r", encoding="utf-8") as startup_file:
        startup_source = startup_file.read()
    check("Disabled pending Revit crash diagnosis" in startup_source, "unsafe Routes adapter enabled")

    gateway_path = os.path.join(
        ROOT, "RccBoq.RestBridge", "src", "RccBoq.RestGateway", "Program.cs"
    )
    with open(gateway_path, "r", encoding="utf-8") as gateway_file:
        gateway_source = gateway_file.read()
    check("127.0.0.1" not in gateway_source, "gateway URL must come from shared constants")
    check("Headers.Authorization" in gateway_source, "Bearer authorization is missing")
    check(gateway_source.count("app.MapPost(") == 2,
          "API must expose exactly two bounded write routes")
    check('"/rcc-boq/elements/{elementId:long}/parameter"' in gateway_source,
          "bounded parameter-write route missing")
    check('"/rcc-boq/boq/last-validation"' in gateway_source,
          "bounded last-export validation route missing")
    check('"/rcc-boq/boq/export-status"' in gateway_source,
          "bounded export-status route missing")
    check('"/rcc-boq/boq/export"' in gateway_source,
          "bounded headless-export route missing")
    check(
        rest_client.endpoint_path("last-validation")
        == "/rcc-boq/boq/last-validation",
        "last-export validation client route missing",
    )
    check(
        rest_client.endpoint_path("export-status")
        == "/rcc-boq/boq/export-status"
        and rest_client.endpoint_path("start-export")
        == "/rcc-boq/boq/export",
        "headless export client routes missing",
    )

    original_local_app_data = os.environ.get("LOCALAPPDATA")
    try:
        with tempfile.TemporaryDirectory() as job_root:
            os.environ["LOCALAPPDATA"] = job_root
            export_root = agent_export_job.agent_export_root()
            os.makedirs(export_root)
            output_path = os.path.join(export_root, "safe-agent-export.xlsx")
            job = {
                "schema": agent_export_job.JOB_SCHEMA,
                "job_id": "12345678-1234-1234-1234-123456789abc",
                "status": "queued",
                "document_title": "QA Model",
                "export_format": "site",
                "include_formwork": True,
                "output_name": os.path.basename(output_path),
                "output_path": output_path,
                "error": "",
            }
            agent_export_job._write_job(job)
            loaded = agent_export_job.load_queued_export_job("QA Model")
            check(loaded is not None, "safe queued Agent export job rejected")
            agent_export_job.mark_export_job_running(loaded)
            agent_export_job.complete_export_job(loaded, {
                "ok": True,
                "workbook_name": os.path.basename(output_path),
                "workbook_sha256": "a" * 64,
                "expected_sheet_count": 2,
                "actual_sheet_count": 2,
                "expected_cell_count": 20,
                "actual_cell_count": 20,
                "mismatch_count": 0,
            })
            with open(agent_export_job.agent_export_job_path(), "r", encoding="utf-8") as job_file:
                completed = json.load(job_file)
            check(
                completed["status"] == "completed"
                and completed["validation"]["mismatch_count"] == 0,
                "Agent export job completion result missing",
            )
            job["status"] = "queued"
            job["output_path"] = os.path.join(job_root, "outside.xlsx")
            agent_export_job._write_job(job)
            check(
                agent_export_job.load_queued_export_job("QA Model") is None,
                "Agent export accepted a path outside its fixed folder",
            )
    finally:
        if original_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = original_local_app_data

    write_service_path = os.path.join(
        ROOT, "RccBoq.RestBridge", "src", "RccBoq.RestRevit", "RevitWriteService.cs"
    )
    with open(write_service_path, "r", encoding="utf-8") as write_file:
        write_source = write_file.read()
    check("request.DryRun" in write_source, "write preview gate missing")
    check("WriteSessionConsent.GetState" in write_source, "write consent gate missing")
    check("transaction.RollBack" in write_source, "transaction rollback missing")
    check("document_saved = false" in write_source, "no-auto-save contract missing")
    check("Evaluate" not in write_source and "InvokeMember" not in write_source,
          "arbitrary execution surface detected")

    with tempfile.TemporaryDirectory() as directory:
        client_token_path = os.path.join(directory, "token.txt")
        with open(client_token_path, "w", encoding="ascii") as token_file:
            token_file.write("a" * 64)
        captured = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b'{"ok":true}'

        original_urlopen = rest_client.urllib.request.urlopen
        try:
            def fake_urlopen(request, timeout):
                captured["request"] = request
                return FakeResponse()

            rest_client.urllib.request.urlopen = fake_urlopen
            status, payload = rest_client.call_api(
                "/rcc-boq/status", token_path=client_token_path
            )
        finally:
            rest_client.urllib.request.urlopen = original_urlopen
        request = captured["request"]
        check(request.get_method() == "GET", "client must use GET")
        check(request.get_header("Authorization") == "Bearer " + "a" * 64,
              "client Bearer token missing")
        check(status == 200 and payload["ok"], "client response parsing failed")

        captured.clear()
        original_urlopen = rest_client.urllib.request.urlopen
        try:
            rest_client.urllib.request.urlopen = fake_urlopen
            status, payload = rest_client.call_api(
                "/rcc-boq/elements/7/parameter",
                token_path=client_token_path,
                body={"parameterName": "Comments", "value": "QA", "dryRun": True},
            )
        finally:
            rest_client.urllib.request.urlopen = original_urlopen
        request = captured["request"]
        check(request.get_method() == "POST", "write client must use POST")
        sent = json.loads(request.data.decode("utf-8"))
        check(sent["dryRun"] is True, "write client must preserve dry-run")
        check(request.get_header("Content-type") == "application/json",
              "write client content type missing")

    with tempfile.TemporaryDirectory() as directory:
        token_path = os.path.join(directory, "private", "token.txt")
        first = rest_api.load_or_create_token(token_path)
        second = rest_api.load_or_create_token(token_path)
        check(first == second and len(first) == 64, "token persistence failed")

    parameters = [FakeParameter("P{0:03d}".format(index), str(index)) for index in range(300)]
    parameters.extend([
        FakeParameter("Quantity", "3"),
        FakeParameter("Bar Length", "11170 mm"),
        FakeParameter("Total Bar Length", "33510 mm"),
        FakeParameter("A", "<varies>"),
        FakeParameter("B", "492 mm"),
    ])
    rebar = FakeElement(3411763, parameters=parameters)
    document = FakeDocument([rebar])
    snapshot = rest_api.element_snapshot(document, rebar)
    check(len(snapshot["parameters"]) == rest_api.MAX_PARAMETERS, "parameter bound failed")
    check(snapshot["parameters_truncated"], "parameter truncation flag missing")

    # Use a smaller record to ensure native BBS values are preserved verbatim.
    sample = FakeElement(7, parameters=parameters[-5:])
    result = rest_api.rebar_snapshot(FakeDocument([sample]), sample)["rebar"]
    check(result["quantity"] == "3", "native quantity lost")
    check(result["total_bar_length"] == "33510 mm", "native total length lost")
    check(result["dimensions"] == {"A": "<varies>", "B": "492 mm"}, "dimensions changed")
    check(result["host_element_id"] == 42, "host ID missing")

    selected = [FakeElement(index, category="Floors") for index in range(150)]
    selection = rest_api.selection_snapshot(FakeDocument(selected), [item.Id for item in selected])
    check(selection["count"] == 150, "selection count wrong")
    check(selection["returned"] == rest_api.MAX_SELECTION, "selection bound failed")
    check(selection["truncated"], "selection truncation flag missing")
    check("path" not in rest_api.document_snapshot(document), "document path leaked")
    print("REST API tests passed")


if __name__ == "__main__":
    run()
