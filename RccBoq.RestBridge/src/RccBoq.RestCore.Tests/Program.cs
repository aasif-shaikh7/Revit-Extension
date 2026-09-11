using RccBoq.RestCore;

string temporaryRoot = Path.Combine(Path.GetTempPath(), $"rcc-boq-rest-tests-{Guid.NewGuid():N}");
Directory.CreateDirectory(temporaryRoot);
try
{
#if RCC_BOQ_SECONDARY
    Assert(BridgeConstants.Channel == "secondary"
        && BridgeConstants.DefaultUrl == "http://127.0.0.1:48886",
        "secondary channel constants");
#else
    Assert(BridgeConstants.Channel == "primary"
        && BridgeConstants.DefaultUrl == "http://127.0.0.1:48885",
        "primary channel constants");
#endif
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
    BridgeRequest rollbackRequest = new(
        "set_parameter",
        3411763,
        "Comments",
        "rollback probe",
        string.Empty,
        false,
        "core-rollback",
        ForceRollback: true);
    await using MemoryStream rollbackStream = new();
    await PipeProtocol.WriteAsync(rollbackStream, rollbackRequest, CancellationToken.None);
    rollbackStream.Position = 0;
    BridgeRequest restoredRollback = await PipeProtocol.ReadAsync<BridgeRequest>(
        rollbackStream,
        CancellationToken.None);
    Assert(restoredRollback == rollbackRequest && restoredRollback.ForceRollback,
        "forced rollback request pipe round trip");
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
