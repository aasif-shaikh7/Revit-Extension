using Autodesk.Revit.UI;

namespace RccBoq.RestRevit;

public sealed class App : IExternalApplication
{
    private BridgeRuntime? _runtime;

    public Result OnStartup(UIControlledApplication application)
    {
        try
        {
            CreateAgentBridgeButton(application);
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
        WriteSessionConsent.Disable();
        _runtime?.Dispose();
        _runtime = null;
        return Result.Succeeded;
    }

    private static void CreateAgentBridgeButton(UIControlledApplication application)
    {
        RibbonPanel panel = application.CreateRibbonPanel("RCC BOQ Agent");
        string assemblyPath = typeof(App).Assembly.Location;
        PushButtonData button = new(
            "RccBoqAgentBridge",
            "Agent\nBridge",
            assemblyPath,
            typeof(AgentBridgeCommand).FullName);
        button.ToolTip = "Inspect bridge status and temporarily enable controlled agent writes.";
        panel.AddItem(button);
    }
}
