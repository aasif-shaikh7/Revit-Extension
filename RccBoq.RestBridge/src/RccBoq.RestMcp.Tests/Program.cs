using System.Text.Json;
using RccBoq.RestMcp;

string input = string.Join('\n',
    "\uFEFF{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\"}}",
    "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}",
    "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}",
    "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_rebar\",\"arguments\":{\"element_id\":3411763}}}",
    "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"rcc_boq_element\",\"arguments\":{\"element_id\":0}}}",
    string.Empty);

using StringReader reader = new(input);
using StringWriter writer = new();
FakeGateway gateway = new();
McpServer server = new(reader, writer, gateway);
await server.RunAsync(CancellationToken.None);

string[] lines = writer.ToString().Split(
    Environment.NewLine,
    StringSplitOptions.RemoveEmptyEntries);
Assert(lines.Length == 4, "response count excludes notification");

using JsonDocument initialize = JsonDocument.Parse(lines[0]);
Assert(initialize.RootElement.GetProperty("result").GetProperty("protocolVersion").GetString()
    == "2025-06-18", "protocol negotiation");

using JsonDocument list = JsonDocument.Parse(lines[1]);
JsonElement tools = list.RootElement.GetProperty("result").GetProperty("tools");
Assert(tools.GetArrayLength() == 5, "tool count");
Assert(tools.EnumerateArray().All(tool =>
    tool.GetProperty("annotations").GetProperty("readOnlyHint").GetBoolean()),
    "read-only annotations");

using JsonDocument call = JsonDocument.Parse(lines[2]);
Assert(!call.RootElement.GetProperty("result").GetProperty("isError").GetBoolean(),
    "successful tool call");
Assert(gateway.Paths.SequenceEqual(new[] { "/rcc-boq/rebar/3411763" }),
    "fixed endpoint allow-list");

using JsonDocument invalid = JsonDocument.Parse(lines[3]);
Assert(invalid.RootElement.GetProperty("error").GetProperty("code").GetInt32() == -32602,
    "invalid element ID rejected");

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

    public Task<GatewayResult> GetAsync(string path, CancellationToken cancellationToken)
    {
        Paths.Add(path);
        return Task.FromResult(new GatewayResult(
            200,
            JsonSerializer.SerializeToElement(new { ok = true, element_id = 3411763 })));
    }
}
