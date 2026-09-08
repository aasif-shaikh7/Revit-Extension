using System.Security.Cryptography;

namespace RccBoq.RestCore;

public sealed class TokenService
{
    public string TokenPath { get; }
    private readonly byte[] _expectedToken;

    public TokenService(string? localApplicationData = null)
    {
        string baseDirectory = localApplicationData
            ?? Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string directory = Path.Combine(baseDirectory, "RCC_BOQ");
        TokenPath = Path.Combine(directory, "rest_token.txt");
        Directory.CreateDirectory(directory);

        string token = File.Exists(TokenPath)
            ? ReadValidToken(TokenPath)
            : CreateOrReadToken(TokenPath);

        _expectedToken = Convert.FromHexString(token);
    }

    private static string CreateOrReadToken(string path)
    {
        string token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
        try
        {
            using FileStream file = new(
                path,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.Read,
                4096,
                FileOptions.WriteThrough);
            using StreamWriter writer = new(file);
            writer.Write(token);
            return token;
        }
        catch (IOException) when (File.Exists(path))
        {
            // A concurrent Gateway startup won the atomic create race.
            return ReadValidToken(path);
        }
    }

    private static string ReadValidToken(string path)
    {
        string token = File.ReadAllText(path).Trim();
        if (!IsValidToken(token))
        {
            throw new InvalidDataException("RCC BOQ REST token file is invalid.");
        }
        return token;
    }

    public bool IsAuthorized(string? authorizationHeader)
    {
        const string prefix = "Bearer ";
        if (authorizationHeader is null
            || !authorizationHeader.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string candidate = authorizationHeader[prefix.Length..].Trim();
        if (!IsValidToken(candidate))
        {
            return false;
        }

        byte[] supplied = Convert.FromHexString(candidate);
        return CryptographicOperations.FixedTimeEquals(_expectedToken, supplied);
    }

    private static bool IsValidToken(string token)
    {
        return token.Length == 64 && token.All(Uri.IsHexDigit);
    }
}
