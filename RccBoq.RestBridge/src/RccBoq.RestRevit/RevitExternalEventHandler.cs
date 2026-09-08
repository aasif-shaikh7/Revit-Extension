using Autodesk.Revit.UI;
using RccBoq.RestCore;

namespace RccBoq.RestRevit;

internal sealed class RevitExternalEventHandler : IExternalEventHandler, IDisposable
{
    private readonly object _sync = new();
    private PendingRequest? _pending;
    private ExternalEvent? _externalEvent;
    private bool _disposed;

    public string GetName() => "RCC BOQ read-only REST bridge";

    public void Attach(ExternalEvent externalEvent)
    {
        _externalEvent = externalEvent;
    }

    public Task<BridgeResponse> DispatchAsync(BridgeRequest request)
    {
        PendingRequest pending = new(request);
        lock (_sync)
        {
            if (_disposed)
            {
                return Task.FromResult(BridgeResponse.Json(
                    503,
                    new { ok = false, error = "Revit bridge is shutting down" }));
            }
            if (_pending is not null)
            {
                return Task.FromResult(BridgeResponse.Json(
                    503,
                    new { ok = false, error = "Revit bridge is busy" }));
            }
            _pending = pending;
        }

        ExternalEventRequest result = _externalEvent?.Raise() ?? ExternalEventRequest.Denied;
        if (result is not ExternalEventRequest.Accepted and not ExternalEventRequest.Pending)
        {
            lock (_sync)
            {
                if (ReferenceEquals(_pending, pending))
                {
                    _pending = null;
                }
            }
            pending.Completion.TrySetResult(BridgeResponse.Json(
                503,
                new { ok = false, error = "Revit rejected the read request" }));
        }
        return pending.Completion.Task;
    }

    public void Execute(UIApplication application)
    {
        PendingRequest? pending;
        lock (_sync)
        {
            pending = _pending;
            _pending = null;
        }
        if (pending is null)
        {
            return;
        }

        try
        {
            pending.Completion.TrySetResult(RevitReadService.Execute(application, pending.Request));
        }
        catch (Exception exception)
        {
            BridgeLog.Write("Revit read failed", exception);
            pending.Completion.TrySetResult(BridgeResponse.Json(
                500,
                new { ok = false, error = "Revit read failed" }));
        }
    }

    public void Dispose()
    {
        PendingRequest? pending;
        lock (_sync)
        {
            _disposed = true;
            pending = _pending;
            _pending = null;
        }
        pending?.Completion.TrySetResult(BridgeResponse.Json(
            503,
            new { ok = false, error = "Revit bridge stopped" }));
    }

    private sealed class PendingRequest(BridgeRequest request)
    {
        public BridgeRequest Request { get; } = request;
        public TaskCompletionSource<BridgeResponse> Completion { get; } = new(
            TaskCreationOptions.RunContinuationsAsynchronously);
    }
}
