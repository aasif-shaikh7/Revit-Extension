namespace RccBoq.RestCore;

public static class RebarValueRules
{
    public static object? NormalizeDimension(object? displayValue, bool hasValue)
    {
        if (!hasValue)
        {
            return "Varies";
        }
        if (displayValue is string text
            && text.Contains("varies", StringComparison.OrdinalIgnoreCase))
        {
            return "Varies";
        }
        return displayValue;
    }
}
