using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RccBoq.RestRevit;

[Transaction(TransactionMode.Manual)]
public sealed class AgentBridgeCommand : IExternalCommand
{
    private static readonly TimeSpan WriteDuration = TimeSpan.FromMinutes(15);

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
                : "Reads and dry-runs are available. Enable a 15-minute session only when you expect an agent to modify parameters.",
            CommonButtons = TaskDialogCommonButtons.Close,
            DefaultButton = TaskDialogResult.Close,
            FooterText = "Localhost/current-user only. Arbitrary code execution, delete, save and document-close operations are not exposed."
        };
        dialog.AddCommandLink(
            TaskDialogCommandLinkId.CommandLink1,
            state.Enabled ? "Renew write access for 15 minutes" : "Enable write access for 15 minutes");
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
}
