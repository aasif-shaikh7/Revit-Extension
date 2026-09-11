using System.Buffers.Binary;
using System.Text;
using System.Text.Json;

namespace RccBoq.RestCore;

public static class BridgeConstants
{
    public const string Version = "2.3.0";
    public const string ApiVersion = "2.3.0";
    public const string ApiName = "rcc-boq";
#if RCC_BOQ_SECONDARY
    public const string Channel = "secondary";
    public const string InstanceMutexName = @"Local\RccBoq.AgentBridge.v2.secondary";
    public const string PipeName = "RccBoq.RevitBridge.v2.secondary";
    public const string DefaultUrl = "http://127.0.0.1:48886";
#else
    public const string Channel = "primary";
    public const string InstanceMutexName = @"Local\RccBoq.AgentBridge.v2";
    public const string PipeName = "RccBoq.RevitBridge.v2";
    public const string DefaultUrl = "http://127.0.0.1:48885";
#endif
    public const int MaxMessageBytes = 1_048_576;
    public const int PipeConnectTimeoutMilliseconds = 1000;
    public const int RequestTimeoutSeconds = 15;
}

public sealed record BridgeRequest(
    string Operation,
    long? ElementId = null,
    string? ParameterName = null,
    string? Value = null,
    string? ExpectedCurrentValue = null,
    bool DryRun = true,
    string? RequestId = null,
    string? ExportFormat = null,
    bool IncludeFormwork = true,
    bool ForceRollback = false);

public sealed record BridgeResponse(int StatusCode, JsonElement Body)
{
    public static BridgeResponse Json(int statusCode, object body)
    {
        return new BridgeResponse(statusCode, JsonSerializer.SerializeToElement(body));
    }
}

public static class PipeProtocol
{
    public static async Task WriteAsync<T>(Stream stream, T value, CancellationToken cancellationToken)
    {
        byte[] payload = JsonSerializer.SerializeToUtf8Bytes(value);
        if (payload.Length > BridgeConstants.MaxMessageBytes)
        {
            throw new InvalidDataException("Bridge message exceeds the configured limit.");
        }

        byte[] length = new byte[sizeof(int)];
        BinaryPrimitives.WriteInt32LittleEndian(length, payload.Length);
        await stream.WriteAsync(length, cancellationToken).ConfigureAwait(false);
        await stream.WriteAsync(payload, cancellationToken).ConfigureAwait(false);
        await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    public static async Task<T> ReadAsync<T>(Stream stream, CancellationToken cancellationToken)
    {
        byte[] length = new byte[sizeof(int)];
        await ReadExactlyAsync(stream, length, cancellationToken).ConfigureAwait(false);
        int payloadLength = BinaryPrimitives.ReadInt32LittleEndian(length);
        if (payloadLength <= 0 || payloadLength > BridgeConstants.MaxMessageBytes)
        {
            throw new InvalidDataException("Invalid bridge message length.");
        }

        byte[] payload = new byte[payloadLength];
        await ReadExactlyAsync(stream, payload, cancellationToken).ConfigureAwait(false);
        return JsonSerializer.Deserialize<T>(payload)
            ?? throw new InvalidDataException("Bridge message is empty.");
    }

    private static async Task ReadExactlyAsync(
        Stream stream,
        byte[] buffer,
        CancellationToken cancellationToken)
    {
        int offset = 0;
        while (offset < buffer.Length)
        {
            int read = await stream.ReadAsync(
                buffer.AsMemory(offset, buffer.Length - offset),
                cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                throw new EndOfStreamException("Bridge connection closed unexpectedly.");
            }
            offset += read;
        }
    }
}
