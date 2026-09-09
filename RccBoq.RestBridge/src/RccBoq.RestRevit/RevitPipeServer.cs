using System.IO.Pipes;
using System.Text.Json;
using RccBoq.RestCore;

namespace RccBoq.RestRevit;

internal sealed class RevitPipeServer : IDisposable
{
    private readonly RevitExternalEventHandler _handler;
    private readonly CancellationTokenSource _shutdown = new();
    private Task? _serverTask;
    private bool _disposed;

    public RevitPipeServer(RevitExternalEventHandler handler)
    {
        _handler = handler;
    }

    public void Start()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _serverTask ??= Task.Run(() => RunAsync(_shutdown.Token));
    }

    private async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await using NamedPipeServerStream pipe = new(
                    BridgeConstants.PipeName,
                    PipeDirection.InOut,
                    1,
                    PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await pipe.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);

                BridgeResponse response;
                try
                {
                    BridgeRequest request = await PipeProtocol.ReadAsync<BridgeRequest>(
                        pipe,
                        cancellationToken).ConfigureAwait(false);
                    string operation = request.Operation?.Trim().ToLowerInvariant() ?? string.Empty;
                    if (!AllowedOperations.Contains(operation))
                    {
                        response = BridgeResponse.Json(
                            400,
                            new { ok = false, error = "Unsupported bridge operation" });
                    }
                    else if ((operation is "element" or "rebar" or "set_parameter")
                             && request.ElementId is null or <= 0)
                    {
                        response = BridgeResponse.Json(
                            400,
                            new { ok = false, error = "A positive element ID is required" });
                    }
                    else if (operation == "status")
                    {
                        // The pipe itself proves that the Revit add-in is alive. Do not
                        // queue a health check behind Revit's ExternalEvent/UI thread.
                        response = BridgeResponse.Json(200, new
                        {
                            ok = true,
                            api = BridgeConstants.ApiName,
                            api_version = BridgeConstants.ApiVersion,
                            extension_version = BridgeConstants.Version,
                            access = "local controlled read-write",
                            write_session = WriteSessionConsent.GetState(),
                            revit_connected = true
                        });
                    }
                    else
                    {
                        response = await _handler.DispatchAsync(
                            request with { Operation = operation }).ConfigureAwait(false);
                    }
                }
                catch (JsonException)
                {
                    response = BridgeResponse.Json(
                        400,
                        new { ok = false, error = "Invalid bridge request" });
                }
                catch (InvalidDataException)
                {
                    response = BridgeResponse.Json(
                        400,
                        new { ok = false, error = "Invalid bridge request" });
                }

                if (pipe.IsConnected)
                {
                    await PipeProtocol.WriteAsync(pipe, response, cancellationToken)
                        .ConfigureAwait(false);
                }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                BridgeLog.Write("Named-pipe request failed", exception);
                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken)
                        .ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    break;
                }
            }
        }
    }

    private static readonly HashSet<string> AllowedOperations = new(
        ["status", "document", "selection", "element", "rebar", "set_parameter"],
        StringComparer.Ordinal);

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }
        _disposed = true;
        _shutdown.Cancel();
        try
        {
            _serverTask?.Wait(TimeSpan.FromSeconds(2));
        }
        catch (AggregateException exception) when (
            exception.InnerExceptions.All(item => item is OperationCanceledException))
        {
            // Expected during Revit shutdown.
        }
        _shutdown.Dispose();
    }
}
