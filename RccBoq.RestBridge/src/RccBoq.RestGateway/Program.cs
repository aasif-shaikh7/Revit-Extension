using System.Diagnostics;
using System.Net;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using RccBoq.RestCore;
using RccBoq.RestGateway;

WebApplicationBuilder builder = WebApplication.CreateSlimBuilder(args);
builder.WebHost.UseUrls(BridgeConstants.DefaultUrl);
builder.WebHost.ConfigureKestrel(options =>
{
    options.AddServerHeader = false;
    options.Limits.MaxRequestBodySize = 16 * 1024;
    options.Limits.RequestHeadersTimeout = TimeSpan.FromSeconds(5);
    options.Limits.KeepAliveTimeout = TimeSpan.FromSeconds(15);
});
builder.Services.AddSingleton<TokenService>();
builder.Services.AddSingleton<RevitPipeClient>();

WebApplication app = builder.Build();
TokenService tokens = app.Services.GetRequiredService<TokenService>();

app.Use(async (context, next) =>
{
    context.Response.Headers.CacheControl = "no-store";
    context.Response.Headers.XContentTypeOptions = "nosniff";
    context.Response.Headers.Append("Content-Security-Policy", "default-src 'none'");

    if (!tokens.IsAuthorized(context.Request.Headers.Authorization))
    {
        context.Response.StatusCode = StatusCodes.Status401Unauthorized;
        await context.Response.WriteAsJsonAsync(new { ok = false, error = "Unauthorized" });
        return;
    }
    await next();
});

static async Task<IResult> ForwardAsync(
    RevitPipeClient pipe,
    BridgeRequest request,
    CancellationToken cancellationToken)
{
    BridgeResponse response = await pipe.SendAsync(request, cancellationToken);
    return Results.Json(response.Body, statusCode: response.StatusCode);
}

app.MapGet("/rcc-boq/status", (RevitPipeClient pipe, CancellationToken token) =>
    ForwardAsync(pipe, new BridgeRequest("status"), token));
app.MapGet("/rcc-boq/document", (RevitPipeClient pipe, CancellationToken token) =>
    ForwardAsync(pipe, new BridgeRequest("document"), token));
app.MapGet("/rcc-boq/selection", (RevitPipeClient pipe, CancellationToken token) =>
    ForwardAsync(pipe, new BridgeRequest("selection"), token));
app.MapGet("/rcc-boq/elements/{elementId:long}",
    (long elementId, RevitPipeClient pipe, CancellationToken token) =>
        ForwardAsync(pipe, new BridgeRequest("element", elementId), token));
app.MapGet("/rcc-boq/rebar/{elementId:long}",
    (long elementId, RevitPipeClient pipe, CancellationToken token) =>
        ForwardAsync(pipe, new BridgeRequest("rebar", elementId), token));
app.MapGet("/rcc-boq/boq/last-validation", (RevitPipeClient pipe, CancellationToken token) =>
    ForwardAsync(pipe, new BridgeRequest("last_export_validation"), token));
app.MapGet("/rcc-boq/boq/export-status", (RevitPipeClient pipe, CancellationToken token) =>
    ForwardAsync(pipe, new BridgeRequest("boq_export_status"), token));
app.MapPost("/rcc-boq/boq/export",
    (StartBoqExportBody body, RevitPipeClient pipe, CancellationToken token) =>
        ForwardAsync(pipe, new BridgeRequest(
            Operation: "start_boq_export",
            DryRun: body.DryRun,
            RequestId: body.RequestId,
            ExportFormat: body.ExportFormat,
            IncludeFormwork: body.IncludeFormwork), token));
app.MapPost("/rcc-boq/elements/{elementId:long}/parameter",
    (long elementId, SetParameterBody body, RevitPipeClient pipe, CancellationToken token) =>
        ForwardAsync(pipe, new BridgeRequest(
            "set_parameter",
            elementId,
            body.ParameterName,
            body.Value,
            body.ExpectedCurrentValue,
            body.DryRun,
            body.RequestId), token));

int? parentProcessId = ParseParentProcessId(args);
if (parentProcessId is not null)
{
    _ = MonitorParentAsync(parentProcessId.Value, app.Lifetime);
}

await app.RunAsync();

static int? ParseParentProcessId(string[] arguments)
{
    int index = Array.IndexOf(arguments, "--parent-pid");
    return index >= 0
        && index + 1 < arguments.Length
        && int.TryParse(arguments[index + 1], out int processId)
            ? processId
            : null;
}

static async Task MonitorParentAsync(int processId, IHostApplicationLifetime lifetime)
{
    try
    {
        using Process parent = Process.GetProcessById(processId);
        await parent.WaitForExitAsync();
    }
    catch (ArgumentException)
    {
        // Parent already exited.
    }
    finally
    {
        lifetime.StopApplication();
    }
}

internal sealed record SetParameterBody(
    string ParameterName,
    string Value,
    string? ExpectedCurrentValue = null,
    bool DryRun = true,
    string? RequestId = null);

internal sealed record StartBoqExportBody(
    string ExportFormat = "site",
    bool IncludeFormwork = true,
    bool DryRun = true,
    string? RequestId = null);
