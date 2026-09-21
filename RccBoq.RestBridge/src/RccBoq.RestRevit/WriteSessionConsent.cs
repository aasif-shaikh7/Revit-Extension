namespace RccBoq.RestRevit;

internal static class WriteSessionConsent
{
    private static readonly object Sync = new();
    private static DateTimeOffset _enabledUntilUtc = DateTimeOffset.MinValue;

    public static DateTimeOffset Enable(TimeSpan duration)
    {
        DateTimeOffset until = DateTimeOffset.UtcNow.Add(duration);
        lock (Sync)
        {
            _enabledUntilUtc = until;
        }
        BridgeLog.Write($"Write session enabled until {until:O}");
        return until;
    }

    public static void Disable()
    {
        lock (Sync)
        {
            _enabledUntilUtc = DateTimeOffset.MinValue;
        }
        BridgeLog.Write("Write session disabled");
    }

    public static WriteSessionState GetState()
    {
        lock (Sync)
        {
            bool enabled = DateTimeOffset.UtcNow < _enabledUntilUtc;
            return new WriteSessionState(
                enabled,
                enabled ? _enabledUntilUtc : null,
                enabled
                    ? Math.Max(0, (int)Math.Ceiling((_enabledUntilUtc - DateTimeOffset.UtcNow).TotalSeconds))
                    : 0);
        }
    }
}

internal sealed record WriteSessionState(
    bool Enabled,
    DateTimeOffset? EnabledUntilUtc,
    int RemainingSeconds);
