using System.Text.Json;
using System.Text.Json.Nodes;
using RccBoq.RestCore;

namespace RccBoq.RestMcp;

internal sealed class McpServer(
    TextReader input,
    TextWriter output,
    IGatewayClient gateway)
{
    private const string ProtocolVersion = "2025-06-18";
    private bool initializeReceived;
    private bool initialized;

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            string? line = await input.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line is null)
            {
                return;
            }
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }
            line = line.TrimStart('\uFEFF');
            if (line.Length > BridgeConstants.MaxMessageBytes)
            {
                await output.WriteLineAsync(
                    Error(null, -32600, "Request exceeds the configured size limit").ToJsonString())
                    .ConfigureAwait(false);
                await output.FlushAsync(cancellationToken).ConfigureAwait(false);
                continue;
            }

            JsonObject? response;
            try
            {
                using JsonDocument message = JsonDocument.Parse(line, new JsonDocumentOptions
                {
                    MaxDepth = 32,
                });
                response = await DispatchAsync(
                    message.RootElement,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (JsonException)
            {
                response = Error(null, -32700, "Parse error");
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                response = Error(null, -32603, $"Internal error: {exception.Message}");
            }

            if (response is not null)
            {
                await output.WriteLineAsync(response.ToJsonString()).ConfigureAwait(false);
                await output.FlushAsync(cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private async Task<JsonObject?> DispatchAsync(
        JsonElement message,
        CancellationToken cancellationToken)
    {
        if (message.ValueKind != JsonValueKind.Object
            || !message.TryGetProperty("jsonrpc", out JsonElement jsonRpc)
            || jsonRpc.GetString() != "2.0"
            || !message.TryGetProperty("method", out JsonElement methodElement)
            || methodElement.ValueKind != JsonValueKind.String)
        {
            return Error(GetId(message), -32600, "Invalid Request");
        }

        JsonNode? id = GetId(message);
        string method = methodElement.GetString()!;
        JsonElement parameters = message.TryGetProperty("params", out JsonElement value)
            ? value
            : default;

        if (id is null)
        {
            if (method == "notifications/initialized")
            {
                initialized = initializeReceived;
            }
            return null;
        }

        return method switch
        {
            "initialize" => Initialize(id, parameters),
            "ping" => Result(id, new JsonObject()),
            "tools/list" when initialized => Result(id, ToolCatalog()),
            "tools/call" when initialized => await CallToolAsync(
                id,
                parameters,
                cancellationToken).ConfigureAwait(false),
            "tools/list" or "tools/call" => Error(id, -32002, "Server is not initialized"),
            _ => Error(id, -32601, "Method not found"),
        };
    }

    private JsonObject Initialize(JsonNode id, JsonElement parameters)
    {
        initializeReceived = true;
        string negotiated = ProtocolVersion;
        if (parameters.ValueKind == JsonValueKind.Object
            && parameters.TryGetProperty("protocolVersion", out JsonElement requested)
            && requested.ValueKind == JsonValueKind.String
            && requested.GetString() is string requestedVersion
            && requestedVersion is "2025-06-18" or "2025-03-26" or "2024-11-05")
        {
            negotiated = requestedVersion;
        }

        return Result(id, new JsonObject
        {
            ["protocolVersion"] = negotiated,
            ["capabilities"] = new JsonObject
            {
                ["tools"] = new JsonObject { ["listChanged"] = false },
            },
            ["serverInfo"] = new JsonObject
            {
                ["name"] = "rcc-boq-revit",
                ["version"] = BridgeConstants.Version,
            },
            ["instructions"] = "Controlled access to the active Revit 2025 document through the local RCC BOQ Agent Bridge. Reads and dry-runs are always available. Actual parameter writes and fixed-folder BOQ exports require the user to enable a short write session from Revit's Agent Bridge pushbutton. Never claim a write or export succeeded unless its result reports completion; the bridge never saves the Revit document automatically.",
        });
    }

    private static JsonObject ToolCatalog()
    {
        JsonArray tools =
        [
            Tool("rcc_boq_status", "Check the local RCC BOQ bridge and Revit connection.", EmptySchema()),
            Tool("rcc_boq_document", "Read bounded identity for the active Revit document.", EmptySchema()),
            Tool("rcc_boq_selection", "Read bounded identity for the current Revit selection.", EmptySchema()),
            Tool("rcc_boq_element", "Read bounded identity and parameters for one Revit element.", ElementSchema()),
            Tool("rcc_boq_rebar", "Read native and derived data for one Revit Rebar element.", ElementSchema()),
            Tool(
                "rcc_boq_last_export_validation",
                "Read the latest bounded canonical BOQ XLSX validation report produced by the exporter.",
                EmptySchema()),
            Tool(
                "rcc_boq_export_status",
                "Read bounded status for the latest Agent Bridge BOQ export job.",
                EmptySchema()),
            Tool(
                "rcc_boq_start_export",
                "Preview or queue a headless BOQ export in the fixed current-user AgentExports folder.",
                StartExportSchema(),
                readOnly: false,
                destructive: false,
                idempotent: false),
            Tool(
                "rcc_boq_set_parameter",
                "Preview or apply one allow-listed Revit parameter edit. Dry-run defaults to true; apply requires temporary user consent in Revit.",
                SetParameterSchema(),
                readOnly: false,
                destructive: true),
        ];
        return new JsonObject { ["tools"] = tools };
    }

    private async Task<JsonObject> CallToolAsync(
        JsonNode id,
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        if (parameters.ValueKind != JsonValueKind.Object
            || !parameters.TryGetProperty("name", out JsonElement nameElement)
            || nameElement.ValueKind != JsonValueKind.String)
        {
            return Error(id, -32602, "Tool name is required");
        }

        string name = nameElement.GetString()!;
        string? path = name switch
        {
            "rcc_boq_status" => "/rcc-boq/status",
            "rcc_boq_document" => "/rcc-boq/document",
            "rcc_boq_selection" => "/rcc-boq/selection",
            "rcc_boq_element" => ElementPath(parameters, "/rcc-boq/elements/"),
            "rcc_boq_rebar" => ElementPath(parameters, "/rcc-boq/rebar/"),
            "rcc_boq_last_export_validation" => "/rcc-boq/boq/last-validation",
            "rcc_boq_export_status" => "/rcc-boq/boq/export-status",
            _ => null,
        };

        if (name == "rcc_boq_set_parameter")
        {
            return await CallSetParameterAsync(id, parameters, cancellationToken)
                .ConfigureAwait(false);
        }

        if (name == "rcc_boq_start_export")
        {
            return await CallStartExportAsync(id, parameters, cancellationToken)
                .ConfigureAwait(false);
        }

        if (path is null)
        {
            return name is "rcc_boq_element" or "rcc_boq_rebar"
                ? Error(id, -32602, "A positive integer element_id is required")
                : Error(id, -32602, $"Unknown tool: {name}");
        }

        try
        {
            GatewayResult gatewayResult = await gateway.GetAsync(
                path,
                cancellationToken).ConfigureAwait(false);
            string body = JsonSerializer.Serialize(
                gatewayResult.Body,
                new JsonSerializerOptions { WriteIndented = true });
            return Result(id, new JsonObject
            {
                ["content"] = new JsonArray
                {
                    new JsonObject { ["type"] = "text", ["text"] = body },
                },
                ["isError"] = !gatewayResult.IsSuccess,
            });
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return Result(id, new JsonObject
            {
                ["content"] = new JsonArray
                {
                    new JsonObject
                    {
                        ["type"] = "text",
                        ["text"] = $"RCC BOQ bridge unavailable: {exception.Message}",
                    },
                },
                ["isError"] = true,
            });
        }
    }

    private async Task<JsonObject> CallSetParameterAsync(
        JsonNode id,
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        if (!TryArguments(parameters, out JsonElement arguments)
            || !arguments.TryGetProperty("element_id", out JsonElement elementId)
            || !elementId.TryGetInt64(out long elementIdValue)
            || elementIdValue <= 0
            || !arguments.TryGetProperty("parameter_name", out JsonElement parameterName)
            || parameterName.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(parameterName.GetString())
            || !arguments.TryGetProperty("value", out JsonElement value)
            || value.ValueKind != JsonValueKind.String)
        {
            return Error(id, -32602, "Positive element_id, parameter_name and string value are required");
        }

        bool dryRun = !arguments.TryGetProperty("dry_run", out JsonElement dryRunElement)
            || dryRunElement.ValueKind != JsonValueKind.False;
        string? expected = OptionalString(arguments, "expected_current_value");
        string? requestId = OptionalString(arguments, "request_id");
        object body = new
        {
            parameterName = parameterName.GetString(),
            value = value.GetString(),
            expectedCurrentValue = expected,
            dryRun,
            requestId
        };
        try
        {
            GatewayResult result = await gateway.PostAsync(
                $"/rcc-boq/elements/{elementIdValue}/parameter",
                body,
                cancellationToken).ConfigureAwait(false);
            return ToolResult(id, result);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return BridgeUnavailable(id, exception);
        }
    }

    private async Task<JsonObject> CallStartExportAsync(
        JsonNode id,
        JsonElement parameters,
        CancellationToken cancellationToken)
    {
        if (!TryArguments(parameters, out JsonElement arguments))
        {
            return Error(id, -32602, "Export arguments are required");
        }
        string format = OptionalString(arguments, "export_format") ?? "site";
        if (format is not ("classic" or "site"))
        {
            return Error(id, -32602, "export_format must be classic or site");
        }
        bool includeFormwork = !arguments.TryGetProperty(
            "include_formwork", out JsonElement formwork)
            || formwork.ValueKind != JsonValueKind.False;
        bool dryRun = !arguments.TryGetProperty("dry_run", out JsonElement dryRunElement)
            || dryRunElement.ValueKind != JsonValueKind.False;
        object body = new
        {
            exportFormat = format,
            includeFormwork,
            dryRun,
            requestId = OptionalString(arguments, "request_id")
        };
        try
        {
            GatewayResult result = await gateway.PostAsync(
                "/rcc-boq/boq/export",
                body,
                cancellationToken).ConfigureAwait(false);
            return ToolResult(id, result);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return BridgeUnavailable(id, exception);
        }
    }

    private static string? ElementPath(JsonElement parameters, string prefix)
    {
        if (!parameters.TryGetProperty("arguments", out JsonElement arguments)
            || arguments.ValueKind != JsonValueKind.Object
            || !arguments.TryGetProperty("element_id", out JsonElement elementId)
            || !elementId.TryGetInt64(out long value)
            || value <= 0)
        {
            return null;
        }
        return prefix + value.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }

    private static JsonObject Tool(
        string name,
        string description,
        JsonObject inputSchema,
        bool readOnly = true,
        bool destructive = false,
        bool idempotent = true) => new()
    {
        ["name"] = name,
        ["description"] = description,
        ["inputSchema"] = inputSchema,
        ["annotations"] = new JsonObject
        {
            ["readOnlyHint"] = readOnly,
            ["destructiveHint"] = destructive,
            ["idempotentHint"] = idempotent,
            ["openWorldHint"] = false,
        },
    };

    private static JsonObject EmptySchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject(),
        ["additionalProperties"] = false,
    };

    private static JsonObject ElementSchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["element_id"] = new JsonObject
            {
                ["type"] = "integer",
                ["minimum"] = 1,
                ["description"] = "Positive Revit element ID.",
            },
        },
        ["required"] = new JsonArray("element_id"),
        ["additionalProperties"] = false,
    };

    private static JsonObject SetParameterSchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["element_id"] = new JsonObject { ["type"] = "integer", ["minimum"] = 1 },
            ["parameter_name"] = new JsonObject { ["type"] = "string", ["minLength"] = 1, ["maxLength"] = 250 },
            ["value"] = new JsonObject { ["type"] = "string", ["maxLength"] = 2000 },
            ["expected_current_value"] = new JsonObject { ["type"] = "string" },
            ["dry_run"] = new JsonObject
            {
                ["type"] = "boolean",
                ["default"] = true,
                ["description"] = "Keep true to preview. False requires a temporary write session enabled in Revit."
            },
            ["request_id"] = new JsonObject { ["type"] = "string", ["maxLength"] = 100 }
        },
        ["required"] = new JsonArray("element_id", "parameter_name", "value"),
        ["additionalProperties"] = false,
    };

    private static JsonObject StartExportSchema() => new()
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["export_format"] = new JsonObject
            {
                ["type"] = "string",
                ["enum"] = new JsonArray("classic", "site"),
                ["default"] = "site"
            },
            ["include_formwork"] = new JsonObject
            {
                ["type"] = "boolean",
                ["default"] = true
            },
            ["dry_run"] = new JsonObject
            {
                ["type"] = "boolean",
                ["default"] = true,
                ["description"] = "False queues one unique fixed-folder export and requires temporary user consent."
            },
            ["request_id"] = new JsonObject { ["type"] = "string", ["maxLength"] = 100 }
        },
        ["additionalProperties"] = false,
    };

    private static bool TryArguments(JsonElement parameters, out JsonElement arguments)
    {
        arguments = default;
        return parameters.ValueKind == JsonValueKind.Object
            && parameters.TryGetProperty("arguments", out arguments)
            && arguments.ValueKind == JsonValueKind.Object;
    }

    private static string? OptionalString(JsonElement arguments, string name)
    {
        return arguments.TryGetProperty(name, out JsonElement value)
            && value.ValueKind == JsonValueKind.String
                ? value.GetString()
                : null;
    }

    private static JsonObject ToolResult(JsonNode id, GatewayResult gatewayResult)
    {
        string body = JsonSerializer.Serialize(
            gatewayResult.Body,
            new JsonSerializerOptions { WriteIndented = true });
        return Result(id, new JsonObject
        {
            ["content"] = new JsonArray
            {
                new JsonObject { ["type"] = "text", ["text"] = body },
            },
            ["isError"] = !gatewayResult.IsSuccess,
        });
    }

    private static JsonObject BridgeUnavailable(JsonNode id, Exception exception)
    {
        return Result(id, new JsonObject
        {
            ["content"] = new JsonArray
            {
                new JsonObject
                {
                    ["type"] = "text",
                    ["text"] = $"RCC BOQ bridge unavailable: {exception.Message}",
                },
            },
            ["isError"] = true,
        });
    }

    private static JsonObject Result(JsonNode id, JsonNode result) => new()
    {
        ["jsonrpc"] = "2.0",
        ["id"] = id.DeepClone(),
        ["result"] = result,
    };

    private static JsonObject Error(JsonNode? id, int code, string message) => new()
    {
        ["jsonrpc"] = "2.0",
        ["id"] = id?.DeepClone(),
        ["error"] = new JsonObject { ["code"] = code, ["message"] = message },
    };

    private static JsonNode? GetId(JsonElement message)
    {
        if (message.ValueKind != JsonValueKind.Object
            || !message.TryGetProperty("id", out JsonElement id)
            || id.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            return null;
        }
        return JsonNode.Parse(id.GetRawText());
    }
}
