using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RccBoq.RestCore;

namespace RccBoq.RestRevit;

internal static class RevitMaterialService
{
    private const int MaxMaterials = 1000;

    private static readonly HashSet<long> AllowedCategoryIds = new(
        [
            (long)BuiltInCategory.OST_StructuralFoundation,
            (long)BuiltInCategory.OST_Floors,
            (long)BuiltInCategory.OST_StructuralFraming,
            (long)BuiltInCategory.OST_StructuralColumns,
            (long)BuiltInCategory.OST_Walls,
        ]);

    public static BridgeResponse List(UIApplication application)
    {
        Document? document = application.ActiveUIDocument?.Document;
        if (document is null)
        {
            return BridgeResponse.Json(409, new { ok = false, error = "No active Revit document" });
        }

        List<MaterialRecord> allMaterials = new FilteredElementCollector(document)
            .OfClass(typeof(Material))
            .Cast<Material>()
            .Select(material => new MaterialRecord(
                material.Id.Value,
                material.Name ?? string.Empty,
                material.MaterialClass ?? string.Empty,
                material.MaterialCategory ?? string.Empty))
            .OrderBy(material => material.Name, StringComparer.OrdinalIgnoreCase)
            .ThenBy(material => material.MaterialId)
            .ToList();
        List<MaterialRecord> returned = allMaterials.Take(MaxMaterials).ToList();

        return BridgeResponse.Json(200, new
        {
            ok = true,
            document_title = document.Title,
            total_count = allMaterials.Count,
            returned_count = returned.Count,
            truncated = allMaterials.Count > returned.Count,
            materials = returned.Select(material => new
            {
                material_id = material.MaterialId,
                name = material.Name,
                material_class = material.MaterialClass,
                material_category = material.MaterialCategory
            })
        });
    }

    public static BridgeResponse SetStructuralMaterial(
        UIApplication application,
        BridgeRequest request)
    {
        Document? document = application.ActiveUIDocument?.Document;
        if (document is null)
        {
            return BridgeResponse.Json(409, new { ok = false, error = "No active Revit document" });
        }
        if (request.ElementId is null or <= 0)
        {
            return BridgeResponse.Json(400, new { ok = false, error = "Invalid element type ID" });
        }
        if (request.MaterialId is null or <= 0)
        {
            return BridgeResponse.Json(400, new { ok = false, error = "Invalid material ID" });
        }
        if (request.ExpectedCurrentMaterialId is < 0)
        {
            return BridgeResponse.Json(400, new
            {
                ok = false,
                error = "Expected current material ID must be zero or a positive integer"
            });
        }

        Element? target = document.GetElement(new ElementId(request.ElementId.Value));
        if (target is not ElementType elementType)
        {
            return BridgeResponse.Json(422, new
            {
                ok = false,
                error = "Target must be a Revit element type"
            });
        }
        long categoryId = elementType.Category?.Id.Value ?? 0;
        if (!AllowedCategoryIds.Contains(categoryId))
        {
            return BridgeResponse.Json(422, new
            {
                ok = false,
                error = "Element type category is not allow-listed for structural material assignment",
                category = elementType.Category?.Name ?? string.Empty
            });
        }

        if (!TryCreateAssignmentTarget(
                elementType, out MaterialAssignmentTarget? assignmentTarget, out string targetError))
        {
            return BridgeResponse.Json(422, new
            {
                ok = false,
                error = targetError
            });
        }

        Material? proposedMaterial = document.GetElement(
            new ElementId(request.MaterialId.Value)) as Material;
        if (proposedMaterial is null)
        {
            return BridgeResponse.Json(404, new { ok = false, error = "Material not found" });
        }

        long? currentMaterialId = assignmentTarget.Read();
        long? expectedMaterialId = NormalizeExpectedMaterialId(
            request.ExpectedCurrentMaterialId);
        if (request.ExpectedCurrentMaterialId.HasValue
            && currentMaterialId != expectedMaterialId)
        {
            return BridgeResponse.Json(409, new
            {
                ok = false,
                error = "Structural Material changed since preview",
                expected_current_material_id = expectedMaterialId,
                current_material = MaterialIdentity(document, currentMaterialId)
            });
        }

        object targetIdentity = TypeIdentity(elementType);
        object currentIdentity = MaterialIdentity(document, currentMaterialId);
        object proposedIdentity = MaterialIdentity(document, proposedMaterial.Id.Value);
        object layerIdentity = MaterialIdentity(
            document, assignmentTarget.ReadLayerMaterial());
        bool wouldChange = currentMaterialId != proposedMaterial.Id.Value;
        if (request.DryRun)
        {
            return BridgeResponse.Json(200, new
            {
                ok = true,
                dry_run = true,
                write_session = WriteSessionConsent.GetState(),
                target_type = targetIdentity,
                current_material = currentIdentity,
                proposed_material = proposedIdentity,
                would_change = wouldChange,
                force_rollback = request.ForceRollback,
                assignment_source = assignmentTarget.Source,
                compound_layer_index = assignmentTarget.CompoundLayerIndex,
                compound_layer_material = layerIdentity
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
        if (!wouldChange && !request.ForceRollback)
        {
            return BridgeResponse.Json(200, new
            {
                ok = true,
                dry_run = false,
                changed = false,
                target_type = targetIdentity,
                previous_material = currentIdentity,
                current_material = currentIdentity,
                transaction = "No change required",
                assignment_source = assignmentTarget.Source,
                compound_layer_index = assignmentTarget.CompoundLayerIndex,
                compound_layer_material = layerIdentity,
                document_saved = false
            });
        }
        if (!wouldChange)
        {
            return BridgeResponse.Json(422, new
            {
                ok = false,
                error = "Forced rollback QA requires a proposed material different from the current material"
            });
        }

        using Transaction transaction = new(document, "RCC BOQ Agent: Set Structural Material");
        try
        {
            transaction.Start();
            if (!assignmentTarget.Set(proposedMaterial.Id)
                || assignmentTarget.Read() != proposedMaterial.Id.Value)
            {
                transaction.RollBack();
                return BridgeResponse.Json(422, new
                {
                    ok = false,
                    error = "Revit rejected the Structural Material value"
                });
            }
            if (request.ForceRollback)
            {
                throw new ForcedRollbackProbeException();
            }
            transaction.Commit();
            long? updatedMaterialId = assignmentTarget.Read();
            if (updatedMaterialId != proposedMaterial.Id.Value)
            {
                return BridgeResponse.Json(500, new
                {
                    ok = false,
                    error = "Structural Material native read-back did not match the committed value"
                });
            }
            object updatedIdentity = MaterialIdentity(document, updatedMaterialId);
            BridgeLog.Write(
                $"MATERIAL WRITE request={SafeRequestId(request.RequestId)} "
                + $"type={elementType.Id.Value} old={currentMaterialId?.ToString() ?? "none"} "
                + $"new={updatedMaterialId?.ToString() ?? "none"}");
            return BridgeResponse.Json(200, new
            {
                ok = true,
                dry_run = false,
                changed = currentMaterialId != updatedMaterialId,
                target_type = targetIdentity,
                previous_material = currentIdentity,
                current_material = updatedIdentity,
                transaction = "RCC BOQ Agent: Set Structural Material",
                assignment_source = assignmentTarget.Source,
                compound_layer_index = assignmentTarget.CompoundLayerIndex,
                compound_layer_material = MaterialIdentity(
                    document, assignmentTarget.ReadLayerMaterial()),
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
            long? restoredMaterialId = assignmentTarget.Read();
            bool rollbackVerified = rollbackStatus == TransactionStatus.RolledBack
                && restoredMaterialId == currentMaterialId;
            if (exception is ForcedRollbackProbeException)
            {
                BridgeLog.Write(
                    $"MATERIAL ROLLBACK QA request={SafeRequestId(request.RequestId)} "
                    + $"type={elementType.Id.Value} verified={rollbackVerified}");
                return BridgeResponse.Json(rollbackVerified ? 200 : 500, new
                {
                    ok = rollbackVerified,
                    dry_run = false,
                    forced_failure = true,
                    rolled_back = rollbackVerified,
                    target_type = targetIdentity,
                    previous_material = currentIdentity,
                    attempted_material = proposedIdentity,
                    current_material = MaterialIdentity(document, restoredMaterialId),
                    transaction = "RCC BOQ Agent: Set Structural Material",
                    transaction_status = rollbackStatus.ToString(),
                    assignment_source = assignmentTarget.Source,
                    compound_layer_index = assignmentTarget.CompoundLayerIndex,
                    compound_layer_material = MaterialIdentity(
                        document, assignmentTarget.ReadLayerMaterial()),
                    document_saved = false
                });
            }
            BridgeLog.Write("Agent Structural Material transaction rolled back", exception);
            return BridgeResponse.Json(422, new
            {
                ok = false,
                error = "Structural Material update failed and was rolled back"
            });
        }
    }

    private static bool TryCreateAssignmentTarget(
        ElementType elementType,
        out MaterialAssignmentTarget target,
        out string error)
    {
        Parameter? parameter = elementType.get_Parameter(
            BuiltInParameter.STRUCTURAL_MATERIAL_PARAM);
        if (parameter is not null && parameter.StorageType != StorageType.ElementId)
        {
            target = null!;
            error = "Structural Material parameter is not an ElementId parameter";
            return false;
        }
        if (parameter is not null && !parameter.IsReadOnly)
        {
            target = new MaterialAssignmentTarget(
                "type_parameter",
                null,
                () => NormalizeMaterialId(parameter.AsElementId()),
                () => NormalizeMaterialId(parameter.AsElementId()),
                materialId => parameter.Set(materialId));
            error = string.Empty;
            return true;
        }

        if (elementType is not HostObjAttributes hostType)
        {
            target = null!;
            error = parameter is null
                ? "Structural Material parameter not found"
                : "Structural Material parameter is read-only and the type has no compound structure";
            return false;
        }
        CompoundStructure? structure = hostType.GetCompoundStructure();
        if (structure is null || structure.LayerCount <= 0)
        {
            target = null!;
            error = "Structural Material is read-only and the type has no compound-structure layers";
            return false;
        }

        int layerIndex = structure.StructuralMaterialIndex;
        if (layerIndex < 0 || layerIndex >= structure.LayerCount)
        {
            List<int> structuralLayers = Enumerable.Range(0, structure.LayerCount)
                .Where(index => structure.GetLayerFunction(index)
                    == MaterialFunctionAssignment.Structure)
                .ToList();
            if (structuralLayers.Count != 1)
            {
                target = null!;
                error = structuralLayers.Count == 0
                    ? "Compound structure has no structural layer"
                    : "Compound structure has multiple structural layers; assignment is ambiguous";
                return false;
            }
            layerIndex = structuralLayers[0];
        }

        int capturedLayerIndex = layerIndex;
        target = new MaterialAssignmentTarget(
            "compound_structure_layer",
            capturedLayerIndex,
            () =>
            {
                CompoundStructure? current = hostType.GetCompoundStructure();
                return current is null
                    || capturedLayerIndex < 0
                    || capturedLayerIndex >= current.LayerCount
                    || current.StructuralMaterialIndex != capturedLayerIndex
                        ? null
                        : NormalizeMaterialId(current.GetMaterialId(capturedLayerIndex));
            },
            () =>
            {
                CompoundStructure? current = hostType.GetCompoundStructure();
                return current is null
                    || capturedLayerIndex < 0
                    || capturedLayerIndex >= current.LayerCount
                        ? null
                        : NormalizeMaterialId(current.GetMaterialId(capturedLayerIndex));
            },
            materialId =>
            {
                CompoundStructure? updated = hostType.GetCompoundStructure();
                if (updated is null
                    || capturedLayerIndex < 0
                    || capturedLayerIndex >= updated.LayerCount)
                {
                    return false;
                }
                updated.SetMaterialId(capturedLayerIndex, materialId);
                if (updated.StructuralMaterialIndex != capturedLayerIndex)
                {
                    updated.StructuralMaterialIndex = capturedLayerIndex;
                }
                hostType.SetCompoundStructure(updated);
                return true;
            });
        error = string.Empty;
        return true;
    }

    private static long? NormalizeMaterialId(ElementId id)
    {
        return id == ElementId.InvalidElementId || id.Value <= 0 ? null : id.Value;
    }

    private static long? NormalizeExpectedMaterialId(long? value)
    {
        return value is null or 0 ? null : value;
    }

    private static object TypeIdentity(ElementType elementType) => new
    {
        element_id = elementType.Id.Value,
        name = elementType.Name ?? string.Empty,
        category = elementType.Category?.Name ?? string.Empty
    };

    private static object MaterialIdentity(Document document, long? materialId)
    {
        Material? material = materialId.HasValue
            ? document.GetElement(new ElementId(materialId.Value)) as Material
            : null;
        return new
        {
            material_id = material?.Id.Value,
            name = material?.Name ?? string.Empty,
            material_class = material?.MaterialClass ?? string.Empty,
            material_category = material?.MaterialCategory ?? string.Empty
        };
    }

    private static string SafeRequestId(string? requestId)
    {
        string value = requestId?.Trim() ?? string.Empty;
        if (value.Length == 0)
        {
            return "none";
        }
        return new string(value.Take(100).Where(character =>
            char.IsLetterOrDigit(character) || character is '-' or '_').ToArray());
    }

    private sealed record MaterialRecord(
        long MaterialId,
        string Name,
        string MaterialClass,
        string MaterialCategory);

    private sealed record MaterialAssignmentTarget(
        string Source,
        int? CompoundLayerIndex,
        Func<long?> Read,
        Func<long?> ReadLayerMaterial,
        Func<ElementId, bool> Set);

    private sealed class ForcedRollbackProbeException : Exception
    {
    }
}
