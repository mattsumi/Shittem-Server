using System.Text.Json;
using System.Text.Json.Serialization;

namespace BlueArchiveAPI.Gateway.Models;

/// <summary>
/// Represents a game session stored in cache
/// </summary>
public class GameSession
{
    /// <summary>
    /// Unique session identifier (UUID)
    /// </summary>
    public string SessionId { get; set; } = string.Empty;
    
    /// <summary>
    /// The MxToken for this session - captured on first occurrence and reused consistently
    /// </summary>
    public string? MxToken { get; set; }
    
    /// <summary>
    /// Account server ID if available
    /// </summary>
    public int? AccountServerId { get; set; }
    
    /// <summary>
    /// Account ID if available
    /// </summary>
    public long? AccountId { get; set; }
    
    /// <summary>
    /// Session creation timestamp
    /// </summary>
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Last access timestamp
    /// </summary>
    public DateTime LastAccessedAt { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Additional session data
    /// </summary>
    public Dictionary<string, object> Data { get; set; } = new();
    
    /// <summary>
    /// Session cookies captured from requests
    /// </summary>
    public Dictionary<string, string> Cookies { get; set; } = new();
    
    /// <summary>
    /// Updates the last accessed timestamp
    /// </summary>
    public void Touch()
    {
        LastAccessedAt = DateTime.UtcNow;
    }
    
    /// <summary>
    /// Captures or retrieves the MxToken for this session
    /// </summary>
    /// <param name="token">Token from incoming request</param>
    /// <returns>The session's consistent MxToken</returns>
    public string CaptureOrGetMxToken(string? token = null)
    {
        if (string.IsNullOrEmpty(MxToken))
        {
            MxToken = token ?? GenerateNewMxToken();
        }
        return MxToken;
    }
    
    /// <summary>
    /// Generates a new 32-byte Base64-encoded random token
    /// </summary>
    private static string GenerateNewMxToken()
    {
        var tokenBytes = new byte[32];
        using (var rng = System.Security.Cryptography.RandomNumberGenerator.Create())
        {
            rng.GetBytes(tokenBytes);
        }
        return Convert.ToBase64String(tokenBytes);
    }
}