using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RccBoq.RestRevit;

[Transaction(TransactionMode.Manual)]
public sealed class AgentBridgeCommand : IExternalCommand
{
    private static readonly TimeSpan WriteDuration = TimeSpan.FromHours(1);
    private static readonly string WriteDurationText = FormatWriteDuration(WriteDuration);

    public Result Execute(
        ExternalCommandData commandData,
        ref string message,
        ElementSet elements)
    {
        WriteSessionState state = WriteSessionConsent.GetState();
        TaskDialog dialog = new("RCC BOQ Agent Bridge")
        {
            MainInstruction = state.Enabled
                ? "Agent write access is temporarily enabled"
                : "Agent bridge is connected in safe read-only mode",
            MainContent = state.Enabled
                ? $"Write access expires at {state.EnabledUntilUtc:O}. Disable it immediately when edits are finished."
                : $"Reads and dry-runs are available. Enable a write session of {WriteDurationText} only when you expect an agent to modify parameters.",
            CommonButtons = TaskDialogCommonButtons.Close,
            DefaultButton = TaskDialogResult.Close,
            FooterText = "Localhost/current-user only. Arbitrary code execution, delete, save and document-close operations are not exposed."
        };
        dialog.AddCommandLink(
            TaskDialogCommandLinkId.CommandLink1,
            state.Enabled
                ? $"Renew write access for {WriteDurationText}"
                : $"Enable write access for {WriteDurationText}");
        if (state.Enabled)
        {
            dialog.AddCommandLink(
                TaskDialogCommandLinkId.CommandLink2,
                "Disable write access now");
        }

        TaskDialogResult result = dialog.Show();
        if (result == TaskDialogResult.CommandLink1)
        {
            DateTimeOffset until = WriteSessionConsent.Enable(WriteDuration);
            TaskDialog.Show(
                "RCC BOQ Agent Bridge",
                $"Write access enabled until {until.ToLocalTime():t}. Revit documents will not be saved automatically.");
        }
        else if (result == TaskDialogResult.CommandLink2)
        {
            WriteSessionConsent.Disable();
            TaskDialog.Show("RCC BOQ Agent Bridge", "Write access disabled. Read-only mode restored.");
        }
        return Result.Succeeded;
    }

    private static string FormatWriteDuration(TimeSpan duration)
    {
        if (duration.TotalMinutes < 60)
        {
            return $"{(int)duration.TotalMinutes} minutes";
        }
        return duration.TotalHours == 1
            ? "1 hour"
            : $"{duration.TotalHours:0.##} hours";
    }
}
