using System.Diagnostics;
using Autodesk.Revit.UI;

namespace RccBoq.RestRevit;

internal sealed class BridgeRuntime : IDisposable
{
    private readonly RevitExternalEventHandler _handler = new();
    private ExternalEvent? _externalEvent;
    private RevitPipeServer? _pipeServer;
    private Process? _gateway;
    private Mutex? _instanceMutex;
    private bool _ownsInstanceMutex;
    private bool _disposed;

    public void Start()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _instanceMutex = new Mutex(false, RccBoq.RestCore.BridgeConstants.InstanceMutexName);
        try
        {
            _ownsInstanceMutex = _instanceMutex.WaitOne(0);
        }
        catch (AbandonedMutexException)
        {
            _ownsInstanceMutex = true;
        }
        if (!_ownsInstanceMutex)
        {
            BridgeLog.Write("Another Revit process already owns the REST bridge; this instance is inactive");
            return;
        }

        _externalEvent = ExternalEvent.Create(_handler);
        _handler.Attach(_externalEvent);
        _pipeServer = new RevitPipeServer(_handler);
        _pipeServer.Start();
        _gateway = StartGateway();
        BridgeLog.Write("RCC BOQ REST bridge started");
    }

    private static Process StartGateway()
    {
        string assemblyDirectory = Path.GetDirectoryName(typeof(App).Assembly.Location)
            ?? throw new InvalidOperationException("Add-in assembly directory is unavailable.");
        string gatewayPath = Path.Combine(
            assemblyDirectory,
            "Gateway",
            "RccBoq.RestGateway.exe");
        if (!File.Exists(gatewayPath))
        {
            throw new FileNotFoundException("REST Gateway executable was not deployed.", gatewayPath);
        }

        ProcessStartInfo startInfo = new()
        {
            FileName = gatewayPath,
            Arguments = $"--parent-pid {Environment.ProcessId}",
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = Path.GetDirectoryName(gatewayPath)!
        };
        return Process.Start(startInfo)
            ?? throw new InvalidOperationException("REST Gateway process did not start.");
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }
        _disposed = true;

        _handler.Dispose();
        _pipeServer?.Dispose();
        _externalEvent?.Dispose();

        try
        {
            if (_gateway is { HasExited: false })
            {
                _gateway.Kill(entireProcessTree: true);
                _gateway.WaitForExit(3000);
            }
        }
        catch (Exception exception)
        {
            BridgeLog.Write("Gateway shutdown failed", exception);
        }
        finally
        {
            _gateway?.Dispose();
        }
        if (_ownsInstanceMutex)
        {
            try
            {
                _instanceMutex?.ReleaseMutex();
            }
            catch (ApplicationException)
            {
                // The mutex was already abandoned during host shutdown.
            }
        }
        _instanceMutex?.Dispose();
        BridgeLog.Write("RCC BOQ REST bridge stopped");
    }
}
