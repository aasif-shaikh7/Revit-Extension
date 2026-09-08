namespace RccBoq.RestRevit;

internal static class BridgeLog
{
    private static readonly object Sync = new();

    public static void Write(string message, Exception? exception = null)
    {
        try
        {
            string directory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "RCC_BOQ",
                "logs");
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, "rest_bridge.log");
            string detail = exception is null
                ? string.Empty
                : $" | {exception.GetType().Name}: {exception.Message}";
            lock (Sync)
            {
                File.AppendAllText(
                    path,
                    $"{DateTimeOffset.Now:O} | {message}{detail}{Environment.NewLine}");
            }
        }
        catch
        {
            // Diagnostics must never destabilize Revit startup or shutdown.
        }
    }
}
