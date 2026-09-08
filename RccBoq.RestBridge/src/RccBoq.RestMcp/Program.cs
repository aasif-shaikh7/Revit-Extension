using RccBoq.RestMcp;

using HttpClient httpClient = new()
{
    BaseAddress = new Uri(GatewayClient.GatewayUrl),
    Timeout = TimeSpan.FromSeconds(20),
};

McpServer server = new(
    Console.In,
    Console.Out,
    new GatewayClient(httpClient));

using CancellationTokenSource shutdown = new();
Console.CancelKeyPress += (_, eventArgs) =>
{
    eventArgs.Cancel = true;
    shutdown.Cancel();
};

await server.RunAsync(shutdown.Token);
