using System.Text.Json;
using RccBoq.RestMcp;

string input = string.Join('\n',
    "\uFEFF{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\"}}",
    "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}",
    "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}",
    "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_rebar\",\"arguments\":{\"element_id\":3411763}}}",
    "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_element\",\"arguments\":{\"element_id\":0}}}",
    "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_set_parameter\",\"arguments\":{\"element_id\":3411763,\"parameter_name\":\"Comments\",\"value\":\"QA\"}}}",
    "{\"jsonrpc\":\"2.0\",\"id\":6,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_last_export_validation\",\"arguments\":{}}}",
    "{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_export_status\",\"arguments\":{}}}",
    "{\"jsonrpc\":\"2.0\",\"id\":8,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_start_export\",\"arguments\":{\"export_format\":\"site\"}}}",
    string.Empty);

using StringReader reader = new(input);
using StringWriter writer = new();
FakeGateway gateway = new();
McpServer server = new(reader, writer, gateway);
await server.RunAsync(CancellationToken.None);

string[] lines = writer.ToString().Split(
    Environment.NewLine,
    StringSplitOptions.RemoveEmptyEntries);
Assert(lines.Length == 8, "response count excludes notification");

using JsonDocument initialize = JsonDocument.Parse(lines[0]);
Assert(initialize.RootElement.GetProperty("result").GetProperty("protocolVersion").GetString()
    == "2025-06-18", "protocol negotiation");

using JsonDocument list = JsonDocument.Parse(lines[1]);
JsonElement tools = list.RootElement.GetProperty("result").GetProperty("tools");
Assert(tools.GetArrayLength() == 9, "tool count");
Assert(tools.EnumerateArray().Take(7).All(tool =>
    tool.GetProperty("annotations").GetProperty("readOnlyHint").GetBoolean()),
    "read-only annotations");
JsonElement exportTool = tools[7];
Assert(!exportTool.GetProperty("annotations").GetProperty("readOnlyHint").GetBoolean(),
    "export tool annotation");
Assert(!exportTool.GetProperty("annotations").GetProperty("destructiveHint").GetBoolean(),
    "export tool non-destructive annotation");
Assert(!exportTool.GetProperty("annotations").GetProperty("idempotentHint").GetBoolean(),
    "export tool non-idempotent annotation");
JsonElement writeTool = tools[8];
Assert(!writeTool.GetProperty("annotations").GetProperty("readOnlyHint").GetBoolean(),
    "write tool annotation");
Assert(writeTool.GetProperty("annotations").GetProperty("destructiveHint").GetBoolean(),
    "write tool destructive annotation");

using JsonDocument call = JsonDocument.Parse(lines[2]);
Assert(!call.RootElement.GetProperty("result").GetProperty("isError").GetBoolean(),
    "successful tool call");
Assert(gateway.Paths.SequenceEqual(new[]
    {
        "/rcc-boq/rebar/3411763",
        "/rcc-boq/boq/last-validation",
        "/rcc-boq/boq/export-status"
    }),
    "fixed endpoint allow-list");

using JsonDocument invalid = JsonDocument.Parse(lines[3]);
Assert(invalid.RootElement.GetProperty("error").GetProperty("code").GetInt32() == -32602,
    "invalid element ID rejected");

using JsonDocument write = JsonDocument.Parse(lines[4]);
Assert(!write.RootElement.GetProperty("result").GetProperty("isError").GetBoolean(),
    "parameter dry-run tool call");
Assert(gateway.PostPaths.SequenceEqual(new[]
    { "/rcc-boq/elements/3411763/parameter", "/rcc-boq/boq/export" }),
    "write endpoint allow-list");
Assert(gateway.PostBodies[0].GetProperty("dryRun").GetBoolean(),
    "parameter edits default to dry-run");

using JsonDocument validation = JsonDocument.Parse(lines[5]);
Assert(!validation.RootElement.GetProperty("result").GetProperty("isError").GetBoolean(),
    "last export validation tool call");

using JsonDocument exportStatus = JsonDocument.Parse(lines[6]);
Assert(!exportStatus.RootElement.GetProperty("result").GetProperty("isError").GetBoolean(),
    "export status tool call");

using JsonDocument startExport = JsonDocument.Parse(lines[7]);
Assert(!startExport.RootElement.GetProperty("result").GetProperty("isError").GetBoolean(),
    "start export dry-run tool call");
Assert(gateway.PostBodies[1].GetProperty("dryRun").GetBoolean(),
    "BOQ export defaults to dry-run");

Console.WriteLine("RCC BOQ MCP tests passed");

static void Assert(bool condition, string name)
{
    if (!condition)
    {
        throw new InvalidOperationException($"Failed: {name}");
    }
}

internal sealed class FakeGateway : IGatewayClient
{
    public List<string> Paths { get; } = [];
    public List<string> PostPaths { get; } = [];
    public List<JsonElement> PostBodies { get; } = [];

    public Task<GatewayResult> GetAsync(string path, CancellationToken cancellationToken)
    {
        Paths.Add(path);
        return Task.FromResult(new GatewayResult(
            200,
            JsonSerializer.SerializeToElement(new { ok = true, element_id = 3411763 })));
    }

    public Task<GatewayResult> PostAsync(
        string path,
        object body,
        CancellationToken cancellationToken)
    {
        PostPaths.Add(path);
        PostBodies.Add(JsonSerializer.SerializeToElement(body));
        return Task.FromResult(new GatewayResult(
            200,
            JsonSerializer.SerializeToElement(new { ok = true, dry_run = true })));
    }
}
