using RccBoq.RestCore;

string temporaryRoot = Path.Combine(Path.GetTempPath(), $"rcc-boq-rest-tests-{Guid.NewGuid():N}");
Directory.CreateDirectory(temporaryRoot);
try
{
    TokenService first = new(temporaryRoot);
    string token = File.ReadAllText(first.TokenPath).Trim();
    Assert(token.Length == 64 && token.All(Uri.IsHexDigit), "token format");
    Assert(first.IsAuthorized($"Bearer {token}"), "valid Bearer token");
    Assert(first.IsAuthorized($"bearer {token}"), "case-insensitive Bearer scheme");
    Assert(!first.IsAuthorized(token), "missing Bearer scheme");
    Assert(!first.IsAuthorized($"Bearer {new string('0', 64)}"), "incorrect token");

    TokenService second = new(temporaryRoot);
    Assert(second.IsAuthorized($"Bearer {token}"), "persisted token");

    BridgeRequest request = new("rebar", 3411763);
    await using MemoryStream stream = new();
    await PipeProtocol.WriteAsync(stream, request, CancellationToken.None);
    stream.Position = 0;
    BridgeRequest restored = await PipeProtocol.ReadAsync<BridgeRequest>(
        stream,
        CancellationToken.None);
    Assert(restored == request, "pipe round trip");
    Assert(
        Equals(RebarValueRules.NormalizeDimension(string.Empty, false), "Varies"),
        "false HasValue varying dimension");
    Assert(
        Equals(RebarValueRules.NormalizeDimension("<varies>", true), "Varies"),
        "display-text varying dimension");
    Assert(
        Equals(RebarValueRules.NormalizeDimension("492 mm", true), "492 mm"),
        "fixed dimension preservation");

    Console.WriteLine("RCC BOQ REST core tests passed");
}
finally
{
    Directory.Delete(temporaryRoot, recursive: true);
}

static void Assert(bool condition, string name)
{
    if (!condition)
    {
        throw new InvalidOperationException($"Failed: {name}");
    }
}
