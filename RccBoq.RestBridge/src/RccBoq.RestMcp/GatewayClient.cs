using System.Net.Http.Headers;
using System.Text.Json;
using RccBoq.RestCore;

namespace RccBoq.RestMcp;

internal interface IGatewayClient
{
    Task<GatewayResult> GetAsync(string path, CancellationToken cancellationToken);
}

internal sealed record GatewayResult(int StatusCode, JsonElement Body)
{
    public bool IsSuccess => StatusCode is >= 200 and < 300;
}

internal sealed class GatewayClient(HttpClient httpClient) : IGatewayClient
{
    internal const string GatewayUrl = BridgeConstants.DefaultUrl;

    public async Task<GatewayResult> GetAsync(
        string path,
        CancellationToken cancellationToken)
    {
        using HttpRequestMessage request = new(HttpMethod.Get, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", ReadToken());
        using HttpResponseMessage response = await httpClient.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);

        await using Stream bodyStream = await response.Content.ReadAsStreamAsync(
            cancellationToken).ConfigureAwait(false);
        using JsonDocument body = await JsonDocument.ParseAsync(
            bodyStream,
            cancellationToken: cancellationToken).ConfigureAwait(false);
        return new GatewayResult((int)response.StatusCode, body.RootElement.Clone());
    }

    private static string ReadToken()
    {
        string localAppData = Environment.GetFolderPath(
            Environment.SpecialFolder.LocalApplicationData);
        string tokenPath = Path.Combine(localAppData, "RCC_BOQ", "rest_token.txt");
        string token = File.ReadAllText(tokenPath).Trim();
        if (token.Length != 64 || !token.All(Uri.IsHexDigit))
        {
            throw new InvalidDataException("RCC BOQ REST token is invalid.");
        }
        return token;
    }
}
