using System.Text.Json;
using System.Text.RegularExpressions;
using Autodesk.Revit.UI;
using RccBoq.RestCore;

namespace RccBoq.RestRevit;

internal static partial class HeadlessBoqExportService
{
    private const string JobSchema = "rcc-boq-agent-export-job/1.0.0";
    private const int MaxJobBytes = 64 * 1024;

    public static BridgeResponse Start(UIApplication application, BridgeRequest request)
    {
        string? documentTitle = application.ActiveUIDocument?.Document?.Title;
        if (string.IsNullOrWhiteSpace(documentTitle))
        {
            return BridgeResponse.Json(409, new { ok = false, error = "No active Revit document" });
        }

        string format = request.ExportFormat?.Trim().ToLowerInvariant() ?? "site";
        if (format is not ("classic" or "site"))
        {
            return BridgeResponse.Json(400, new
            {
                ok = false,
                error = "Export format must be classic or site"
            });
        }

        RevitCommandId? commandId = FindBoqCommand(application);
        if (commandId is null)
        {
            return BridgeResponse.Json(409, new
            {
                ok = false,
                error = "The Nudge RCC BOQ pyRevit command is unavailable"
            });
        }

        WriteSessionState session = WriteSessionConsent.GetState();
        if (request.DryRun)
        {
            return BridgeResponse.Json(200, new
            {
                ok = true,
                dry_run = true,
                export_format = format,
                include_formwork = request.IncludeFormwork,
                output_policy = "Unique XLSX in current-user RCC_BOQ/AgentExports",
                command_available = true,
                write_session = session,
                document_saved = false
            });
        }
        if (!session.Enabled)
        {
            return BridgeResponse.Json(403, new
            {
                ok = false,
                error = "Write session is disabled; enable it from the Revit Agent Bridge pushbutton"
            });
        }
        if (HasActiveJob())
        {
            return BridgeResponse.Json(409, new
            {
                ok = false,
                error = "A BOQ export job is already queued or running"
            });
        }

        string jobId = Guid.NewGuid().ToString("D");
        string outputDirectory = ExportDirectory();
        Directory.CreateDirectory(outputDirectory);
        string outputName = $"{DateTime.Now:yyyyMMdd-HHmmss}-{SafeName(documentTitle)}-AGENT-BOQ-{jobId[..8]}.xlsx";
        string outputPath = Path.Combine(outputDirectory, outputName);
        object job = new
        {
            schema = JobSchema,
            job_id = jobId,
            status = "queued",
            created_at_utc = DateTimeOffset.UtcNow.ToString("O"),
            document_title = documentTitle,
            export_format = format,
            include_formwork = request.IncludeFormwork,
            output_name = outputName,
            output_path = outputPath,
            request_id = SafeRequestId(request.RequestId),
            error = string.Empty
        };
        WriteJob(job);

        try
        {
            application.PostCommand(commandId);
        }
        catch (Exception exception)
        {
            WriteFailedJob(jobId, documentTitle, format, request.IncludeFormwork,
                outputName, outputPath, request.RequestId, exception.Message);
            return BridgeResponse.Json(409, new
            {
                ok = false,
                error = "Revit could not queue the RCC BOQ command"
            });
        }

        BridgeLog.Write($"BOQ EXPORT queued job={jobId} format={format} output={outputName}");
        return BridgeResponse.Json(202, new
        {
            ok = true,
            dry_run = false,
            job_id = jobId,
            status = "queued",
            export_format = format,
            include_formwork = request.IncludeFormwork,
            output_name = outputName,
            document_saved = false
        });
    }

    public static BridgeResponse Status(UIApplication application)
    {
        string path = JobPath();
        FileInfo file = new(path);
        if (!file.Exists)
        {
            return BridgeResponse.Json(404, new
            {
                ok = false,
                error = "No BOQ export job is available"
            });
        }
        if (file.Length is <= 0 or > MaxJobBytes)
        {
            return InvalidJob();
        }
        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllBytes(path));
            JsonElement root = document.RootElement;
            if (Text(root, "schema") != JobSchema)
            {
                return InvalidJob();
            }
            string reportTitle = Text(root, "document_title");
            string activeTitle = application.ActiveUIDocument?.Document?.Title ?? string.Empty;
            JsonElement? validation = root.TryGetProperty("validation", out JsonElement value)
                ? value.Clone()
                : null;
            return BridgeResponse.Json(200, new
            {
                ok = true,
                job = new
                {
                    job_id = Limit(Text(root, "job_id"), 36),
                    status = Limit(Text(root, "status"), 20),
                    created_at_utc = Limit(Text(root, "created_at_utc"), 50),
                    started_at_utc = Limit(Text(root, "started_at_utc"), 50),
                    completed_at_utc = Limit(Text(root, "completed_at_utc"), 50),
                    document_title = Limit(reportTitle, 250),
                    matches_active_document = activeTitle.Length > 0
                        && string.Equals(activeTitle, reportTitle, StringComparison.Ordinal),
                    export_format = Limit(Text(root, "export_format"), 20),
                    include_formwork = Boolean(root, "include_formwork"),
                    output_name = Limit(Text(root, "output_name"), 250),
                    error = Limit(Text(root, "error"), 500),
                    validation
                }
            });
        }
        catch (JsonException)
        {
            return InvalidJob();
        }
        catch (IOException)
        {
            return BridgeResponse.Json(503, new
            {
                ok = false,
                error = "BOQ export job is temporarily unavailable"
            });
        }
    }

    private static RevitCommandId? FindBoqCommand(UIApplication application)
    {
        foreach (string name in CommandNames)
        {
            try
            {
                RevitCommandId? command = RevitCommandId.LookupCommandId(name);
                if (command is not null && application.CanPostCommand(command))
                {
                    return command;
                }
            }
            catch
            {
                // Try the next known pyRevit command identifier.
            }
        }
        return null;
    }

    private static bool HasActiveJob()
    {
        try
        {
            FileInfo file = new(JobPath());
            if (!file.Exists || file.Length is <= 0 or > MaxJobBytes)
            {
                return false;
            }
            using JsonDocument job = JsonDocument.Parse(File.ReadAllBytes(file.FullName));
            string status = Text(job.RootElement, "status");
            if (status is not ("queued" or "running"))
            {
                return false;
            }
            return DateTimeOffset.TryParse(
                Text(job.RootElement, "created_at_utc"),
                out DateTimeOffset created)
                && DateTimeOffset.UtcNow - created < TimeSpan.FromMinutes(30);
        }
        catch
        {
            return false;
        }
    }

    private static void WriteFailedJob(
        string jobId,
        string documentTitle,
        string format,
        bool includeFormwork,
        string outputName,
        string outputPath,
        string? requestId,
        string error)
    {
        WriteJob(new
        {
            schema = JobSchema,
            job_id = jobId,
            status = "failed",
            created_at_utc = DateTimeOffset.UtcNow.ToString("O"),
            completed_at_utc = DateTimeOffset.UtcNow.ToString("O"),
            document_title = documentTitle,
            export_format = format,
            include_formwork = includeFormwork,
            output_name = outputName,
            output_path = outputPath,
            request_id = SafeRequestId(requestId),
            error = Limit(error, 500)
        });
    }

    private static void WriteJob(object job)
    {
        string path = JobPath();
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        byte[] payload = JsonSerializer.SerializeToUtf8Bytes(job, new JsonSerializerOptions
        {
            WriteIndented = true
        });
        if (payload.Length > MaxJobBytes)
        {
            throw new InvalidDataException("BOQ export job exceeds the configured limit");
        }
        string temporaryPath = path + ".tmp";
        File.WriteAllBytes(temporaryPath, payload);
        File.Move(temporaryPath, path, true);
    }

    private static BridgeResponse InvalidJob() => BridgeResponse.Json(422, new
    {
        ok = false,
        error = "BOQ export job is invalid"
    });

    private static string ExportDirectory() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "RCC_BOQ",
        "AgentExports");

    private static string JobPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "RCC_BOQ",
        "boq_export_job.json");

    private static string SafeName(string value)
    {
        string safe = UnsafeFileCharacters().Replace(value, "-").Trim('-');
        if (safe.Length == 0)
        {
            safe = "Revit-Project";
        }
        return Limit(safe, 80);
    }

    private static string SafeRequestId(string? value)
    {
        string text = value?.Trim() ?? string.Empty;
        return new string(text.Take(100).Where(character =>
            char.IsLetterOrDigit(character) || character is '-' or '_').ToArray());
    }

    private static string Text(JsonElement root, string name) =>
        root.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;

    private static bool Boolean(JsonElement root, string name) =>
        root.TryGetProperty(name, out JsonElement value)
        && value.ValueKind is JsonValueKind.True or JsonValueKind.False
        && value.GetBoolean();

    private static string Limit(string? value, int length)
    {
        string text = value ?? string.Empty;
        return text.Length <= length ? text : text[..length];
    }

    [GeneratedRegex("[^A-Za-z0-9._-]+")]
    private static partial Regex UnsafeFileCharacters();

    private static readonly string[] CommandNames =
    [
        "CustomCtrl_%CustomCtrl_%Nudge%Generate%BOQ",
        "CustomCtrl_%Nudge%Generate%BOQ",
        "CustomCtrl_%Nudge%Generate%RCC BOQ"
    ];
}
