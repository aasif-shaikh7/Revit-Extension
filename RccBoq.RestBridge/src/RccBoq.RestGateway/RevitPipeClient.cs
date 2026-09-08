using System.IO.Pipes;
using RccBoq.RestCore;

namespace RccBoq.RestGateway;

public sealed class RevitPipeClient
{
    private readonly SemaphoreSlim _singleRequest = new(1, 1);

    public async Task<BridgeResponse> SendAsync(
        BridgeRequest request,
        CancellationToken cancellationToken)
    {
        await _singleRequest.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            await using NamedPipeClientStream pipe = new(
                ".",
                BridgeConstants.PipeName,
                PipeDirection.InOut,
                PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
            await pipe.ConnectAsync(
                BridgeConstants.PipeConnectTimeoutMilliseconds,
                cancellationToken).ConfigureAwait(false);

            using CancellationTokenSource responseTimeout =
                CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            responseTimeout.CancelAfter(
                TimeSpan.FromSeconds(BridgeConstants.RequestTimeoutSeconds));
            await PipeProtocol.WriteAsync(pipe, request, responseTimeout.Token).ConfigureAwait(false);
            return await PipeProtocol.ReadAsync<BridgeResponse>(pipe, responseTimeout.Token)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return BridgeResponse.Json(504, new { ok = false, error = "Revit bridge timed out" });
        }
        catch (Exception exception) when (
            exception is IOException
            or TimeoutException
            or UnauthorizedAccessException)
        {
            return BridgeResponse.Json(503, new { ok = false, error = "Revit bridge unavailable" });
        }
        finally
        {
            _singleRequest.Release();
        }
    }
}
