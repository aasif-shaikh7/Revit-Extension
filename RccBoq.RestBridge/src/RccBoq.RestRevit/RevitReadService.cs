using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.UI;
using RccBoq.RestCore;

namespace RccBoq.RestRevit;

internal static class RevitReadService
{
    private const int MaxSelection = 100;
    private const int MaxParameters = 250;
    private const int MaxTextLength = 1000;

    public static BridgeResponse Execute(UIApplication application, BridgeRequest request)
    {
        return request.Operation switch
        {
            "status" => BridgeResponse.Json(200, new
            {
                ok = true,
                api = BridgeConstants.ApiName,
                api_version = BridgeConstants.ApiVersion,
                extension_version = BridgeConstants.Version,
                revit_context = true
            }),
            "document" => DocumentResponse(application),
            "selection" => SelectionResponse(application),
            "element" => ElementResponse(application, request.ElementId, false),
            "rebar" => ElementResponse(application, request.ElementId, true),
            _ => BridgeResponse.Json(400, new { ok = false, error = "Unsupported operation" })
        };
    }

    private static BridgeResponse DocumentResponse(UIApplication application)
    {
        Document? document = application.ActiveUIDocument?.Document;
        if (document is null)
        {
            return NoDocument();
        }
        return BridgeResponse.Json(200, new
        {
            ok = true,
            document = new
            {
                title = Limit(document.Title, 250),
                is_family_document = document.IsFamilyDocument,
                revit_version = Limit(application.Application.VersionNumber, 50),
                revit_build = Limit(application.Application.VersionBuild, 100)
            }
        });
    }

    private static BridgeResponse SelectionResponse(UIApplication application)
    {
        UIDocument? uiDocument = application.ActiveUIDocument;
        if (uiDocument is null)
        {
            return NoDocument();
        }

        List<ElementId> ids = uiDocument.Selection.GetElementIds().ToList();
        List<object> elements = ids
            .Take(MaxSelection)
            .Select(uiDocument.Document.GetElement)
            .Where(element => element is not null)
            .Select(element => ElementSnapshot(uiDocument.Document, element!, false))
            .Cast<object>()
            .ToList();
        return BridgeResponse.Json(200, new
        {
            ok = true,
            selection = new
            {
                count = ids.Count,
                returned = elements.Count,
                truncated = ids.Count > MaxSelection,
                elements
            }
        });
    }

    private static BridgeResponse ElementResponse(
        UIApplication application,
        long? elementId,
        bool requireRebar)
    {
        Document? document = application.ActiveUIDocument?.Document;
        if (document is null)
        {
            return NoDocument();
        }
        if (elementId is null or <= 0)
        {
            return BridgeResponse.Json(400, new { ok = false, error = "Invalid element ID" });
        }

        Element? element = document.GetElement(new ElementId(elementId.Value));
        if (element is null)
        {
            return BridgeResponse.Json(404, new { ok = false, error = "Element not found" });
        }
        if (requireRebar && element is not Rebar)
        {
            return BridgeResponse.Json(422, new { ok = false, error = "Element is not Rebar" });
        }

        object snapshot = requireRebar
            ? RebarSnapshot(document, (Rebar)element)
            : ElementSnapshot(document, element, true);
        return BridgeResponse.Json(200, new { ok = true, element = snapshot });
    }

    private static Dictionary<string, object?> ElementSnapshot(
        Document document,
        Element element,
        bool parameters)
    {
        ElementId typeId = element.GetTypeId();
        ElementType? elementType = typeId == ElementId.InvalidElementId
            ? null
            : document.GetElement(typeId) as ElementType;

        List<object>? records = parameters ? ParameterRecords(element) : null;
        return new Dictionary<string, object?>
        {
            ["element_id"] = element.Id.Value,
            ["name"] = Limit(element.Name, 250),
            ["category"] = Limit(element.Category?.Name, 250),
            ["unique_id"] = Limit(element.UniqueId, 250),
            ["type_id"] = typeId == ElementId.InvalidElementId ? null : typeId.Value,
            ["type_name"] = Limit(elementType?.Name, 250),
            ["family_name"] = Limit(elementType?.FamilyName, 250),
            ["parameters"] = records,
            ["parameters_truncated"] = parameters && element.Parameters.Size > MaxParameters
        };
    }

    private static object RebarSnapshot(Document document, Rebar rebar)
    {
        Dictionary<string, object?> named = NamedParameters(rebar);
        Dictionary<string, object?> dimensions = new(StringComparer.OrdinalIgnoreCase);
        foreach (string name in DimensionNames)
        {
            object? value = First(named, name);
            bool hasValue = ParameterHasValue(rebar, name) ?? true;
            object? normalized = RebarValueRules.NormalizeDimension(value, hasValue);
            if (!IsEmpty(normalized))
            {
                dimensions[name] = normalized;
            }
        }

        Dictionary<string, object?> snapshot = ElementSnapshot(document, rebar, true);
        snapshot["rebar"] = new
            {
                quantity = First(named, "Quantity", "Bar Quantity"),
                bar_length = First(named, "Bar Length"),
                total_bar_length = First(named, "Total Bar Length", "Total Length"),
                diameter = First(named, "Bar Diameter", "Diameter"),
                shape = First(named, "Shape", "Rebar Shape"),
                bar_mark = First(named, "Bar Mark", "Schedule Mark", "Mark"),
                host_mark = First(named, "Host Mark"),
                bend_diameter = First(named, "Bend Diameter"),
                start_hook = First(named, "Hook At Start", "Start Hook"),
                end_hook = First(named, "Hook At End", "End Hook"),
                dimensions,
                host_element_id = ValidId(rebar.GetHostId()),
                has_variable_length_bars = HasVariableLengthBars(rebar),
                length_source = "Native Revit parameters; no custom bend deduction"
            };
        return snapshot;
    }

    private static List<object> ParameterRecords(Element element)
    {
        Dictionary<string, object?> named = NamedParameters(element);
        return named
            .OrderBy(item => item.Key, StringComparer.OrdinalIgnoreCase)
            .Take(MaxParameters)
            .Select(item => (object)new { name = Limit(item.Key, 250), value = item.Value })
            .ToList();
    }

    private static Dictionary<string, object?> NamedParameters(Element element)
    {
        Dictionary<string, object?> result = new(StringComparer.OrdinalIgnoreCase);
        foreach (Parameter parameter in element.Parameters)
        {
            string name;
            try
            {
                name = parameter.Definition?.Name ?? string.Empty;
            }
            catch
            {
                continue;
            }
            if (string.IsNullOrWhiteSpace(name) || result.ContainsKey(name))
            {
                continue;
            }
            result[name] = ParameterValue(parameter);
        }
        return result;
    }

    private static object? ParameterValue(Parameter parameter)
    {
        bool hasValue;
        try
        {
            hasValue = parameter.HasValue;
        }
        catch
        {
            hasValue = true;
        }

        // Revit represents a varying Rebar dimension as display text even when
        // HasValue is false. Read display accessors before honoring HasValue.
        try
        {
            string? value = parameter.AsString();
            if (!string.IsNullOrEmpty(value))
            {
                return Limit(value, MaxTextLength);
            }
        }
        catch
        {
            // Continue to the display/raw value.
        }
        try
        {
            string? value = parameter.AsValueString();
            if (!string.IsNullOrEmpty(value))
            {
                return Limit(value, MaxTextLength);
            }
        }
        catch
        {
            // Continue to the raw value.
        }
        if (!hasValue)
        {
            return string.Empty;
        }

        try
        {
            return parameter.StorageType switch
            {
                StorageType.Integer => parameter.AsInteger(),
                StorageType.Double => parameter.AsDouble(),
                StorageType.ElementId => ValidId(parameter.AsElementId()),
                _ => string.Empty
            };
        }
        catch
        {
            return string.Empty;
        }
    }

    private static object? First(Dictionary<string, object?> values, params string[] names)
    {
        foreach (string name in names)
        {
            if (values.TryGetValue(name, out object? value) && !IsEmpty(value))
            {
                return value;
            }
        }
        return string.Empty;
    }

    private static bool IsEmpty(object? value) => value is null || value is string text && text.Length == 0;

    private static bool? HasVariableLengthBars(Rebar rebar)
    {
        try
        {
            return rebar.HasVariableLengthBars;
        }
        catch
        {
            return null;
        }
    }

    private static bool? ParameterHasValue(Element element, string name)
    {
        try
        {
            return element.LookupParameter(name)?.HasValue;
        }
        catch
        {
            return null;
        }
    }

    private static long? ValidId(ElementId? id)
    {
        return id is null || id == ElementId.InvalidElementId ? null : id.Value;
    }

    private static string Limit(string? value, int length)
    {
        string text = value ?? string.Empty;
        return text.Length <= length ? text : text[..length];
    }

    private static BridgeResponse NoDocument()
    {
        return BridgeResponse.Json(409, new { ok = false, error = "No active Revit document" });
    }

    private static readonly string[] DimensionNames =
    [
        "A", "B", "C", "C1", "C2", "D", "D1", "D2", "E", "F", "G", "H",
        "J", "K", "O", "P", "Q", "R", "S", "V", "W"
    ];
}
