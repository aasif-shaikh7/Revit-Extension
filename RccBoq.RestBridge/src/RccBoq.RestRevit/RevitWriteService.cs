using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RccBoq.RestCore;

namespace RccBoq.RestRevit;

internal static class RevitWriteService
{
    private const int MaxParameterNameLength = 250;
    private const int MaxValueLength = 2000;

    public static BridgeResponse SetParameter(UIApplication application, BridgeRequest request)
    {
        Document? document = application.ActiveUIDocument?.Document;
        if (document is null)
        {
            return BridgeResponse.Json(409, new { ok = false, error = "No active Revit document" });
        }
        if (request.ElementId is null or <= 0)
        {
            return BridgeResponse.Json(400, new { ok = false, error = "Invalid element ID" });
        }
        string parameterName = request.ParameterName?.Trim() ?? string.Empty;
        if (parameterName.Length is 0 or > MaxParameterNameLength)
        {
            return BridgeResponse.Json(400, new { ok = false, error = "Invalid parameter name" });
        }
        string value = request.Value ?? string.Empty;
        if (value.Length > MaxValueLength)
        {
            return BridgeResponse.Json(400, new { ok = false, error = "Parameter value is too long" });
        }

        Element? element = document.GetElement(new ElementId(request.ElementId.Value));
        if (element is null)
        {
            return BridgeResponse.Json(404, new { ok = false, error = "Element not found" });
        }
        IList<Parameter> matches = element.GetParameters(parameterName);
        if (matches.Count == 0)
        {
            return BridgeResponse.Json(404, new { ok = false, error = "Parameter not found" });
        }
        if (matches.Count != 1)
        {
            return BridgeResponse.Json(409, new
            {
                ok = false,
                error = "Parameter name is ambiguous on this element",
                matches = matches.Count
            });
        }
        Parameter parameter = matches[0];
        if (parameter.IsReadOnly)
        {
            return BridgeResponse.Json(422, new { ok = false, error = "Parameter is read-only" });
        }
        if (parameter.StorageType == StorageType.ElementId)
        {
            return BridgeResponse.Json(422, new
            {
                ok = false,
                error = "ElementId parameter writes are not supported by this safe operation"
            });
        }

        string current = DisplayValue(parameter);
        if (request.ExpectedCurrentValue is not null
            && !string.Equals(current, request.ExpectedCurrentValue, StringComparison.Ordinal))
        {
            return BridgeResponse.Json(409, new
            {
                ok = false,
                error = "Parameter changed since preview",
                expected = request.ExpectedCurrentValue,
                current
            });
        }
        if (request.DryRun)
        {
            return BridgeResponse.Json(200, new
            {
                ok = true,
                dry_run = true,
                write_session = WriteSessionConsent.GetState(),
                element_id = request.ElementId,
                parameter = parameterName,
                storage_type = parameter.StorageType.ToString(),
                current,
                proposed = value,
                would_change = !string.Equals(current, value, StringComparison.Ordinal),
                force_rollback = request.ForceRollback
            });
        }
        WriteSessionState session = WriteSessionConsent.GetState();
        if (!session.Enabled)
        {
            return BridgeResponse.Json(403, new
            {
                ok = false,
                error = "Write session is disabled; enable it from the Revit Agent Bridge pushbutton"
            });
        }

        using Transaction transaction = new(document, "RCC BOQ Agent: Set Parameter");
        try
        {
            transaction.Start();
            bool changed = SetValue(parameter, value);
            if (!changed)
            {
                transaction.RollBack();
                return BridgeResponse.Json(422, new { ok = false, error = "Revit rejected the parameter value" });
            }
            if (request.ForceRollback)
            {
                throw new ForcedRollbackProbeException();
            }
            transaction.Commit();
            string updated = DisplayValue(parameter);
            BridgeLog.Write(
                $"WRITE request={SafeRequestId(request.RequestId)} element={request.ElementId} parameter={parameterName} old={current} new={updated}");
            return BridgeResponse.Json(200, new
            {
                ok = true,
                dry_run = false,
                changed = !string.Equals(current, updated, StringComparison.Ordinal),
                element_id = request.ElementId,
                parameter = parameterName,
                previous = current,
                current = updated,
                transaction = "RCC BOQ Agent: Set Parameter",
                document_saved = false
            });
        }
        catch (Exception exception)
        {
            TransactionStatus rollbackStatus = transaction.GetStatus();
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                rollbackStatus = transaction.RollBack();
            }
            string restored = DisplayValue(parameter);
            bool rollbackVerified = rollbackStatus == TransactionStatus.RolledBack
                && string.Equals(current, restored, StringComparison.Ordinal);
            if (exception is ForcedRollbackProbeException)
            {
                BridgeLog.Write(
                    $"ROLLBACK QA request={SafeRequestId(request.RequestId)} element={request.ElementId} parameter={parameterName} verified={rollbackVerified}");
                return BridgeResponse.Json(rollbackVerified ? 200 : 500, new
                {
                    ok = rollbackVerified,
                    dry_run = false,
                    forced_failure = true,
                    rolled_back = rollbackVerified,
                    element_id = request.ElementId,
                    parameter = parameterName,
                    previous = current,
                    attempted = value,
                    current = restored,
                    transaction = "RCC BOQ Agent: Set Parameter",
                    transaction_status = rollbackStatus.ToString(),
                    document_saved = false
                });
            }
            BridgeLog.Write("Agent parameter transaction rolled back", exception);
            return BridgeResponse.Json(422, new { ok = false, error = "Parameter update failed and was rolled back" });
        }
    }

    private static bool SetValue(Parameter parameter, string value)
    {
        return parameter.StorageType switch
        {
            StorageType.String => parameter.Set(value),
            StorageType.Integer => int.TryParse(
                value,
                System.Globalization.NumberStyles.Integer,
                System.Globalization.CultureInfo.InvariantCulture,
                out int integer) && parameter.Set(integer),
            StorageType.Double => parameter.SetValueString(value),
            _ => false
        };
    }

    private static string DisplayValue(Parameter parameter)
    {
        try
        {
            if (parameter.StorageType == StorageType.String)
            {
                return parameter.AsString() ?? string.Empty;
            }
            string? formatted = parameter.AsValueString();
            if (!string.IsNullOrEmpty(formatted))
            {
                return formatted;
            }
            return parameter.StorageType switch
            {
                StorageType.Integer => parameter.AsInteger().ToString(
                    System.Globalization.CultureInfo.InvariantCulture),
                StorageType.Double => parameter.AsDouble().ToString(
                    "R",
                    System.Globalization.CultureInfo.InvariantCulture),
                _ => string.Empty
            };
        }
        catch
        {
            return string.Empty;
        }
    }

    private static string SafeRequestId(string? requestId)
    {
        string value = requestId?.Trim() ?? string.Empty;
        if (value.Length == 0)
        {
            return "none";
        }
        return new string(value.Take(100).Where(character => char.IsLetterOrDigit(character) || character is '-' or '_').ToArray());
    }

    private sealed class ForcedRollbackProbeException : Exception
    {
    }
}
