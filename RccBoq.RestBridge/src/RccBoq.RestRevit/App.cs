using Autodesk.Revit.UI;

namespace RccBoq.RestRevit;

public sealed class App : IExternalApplication
{
    private BridgeRuntime? _runtime;

    public Result OnStartup(UIControlledApplication application)
    {
        try
        {
            _runtime = new BridgeRuntime();
            _runtime.Start();
            return Result.Succeeded;
        }
        catch (Exception exception)
        {
            BridgeLog.Write("Startup failed", exception);
            _runtime?.Dispose();
            _runtime = null;
            return Result.Failed;
        }
    }

    public Result OnShutdown(UIControlledApplication application)
    {
        _runtime?.Dispose();
        _runtime = null;
        return Result.Succeeded;
    }
}
