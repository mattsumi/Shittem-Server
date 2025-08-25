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
    /// Account server ID captured from official responses or generated for the session
    /// </summary>
    public int? AccountServerId { get; set; }
    
    /// <summary>
    /// Account ID captured from official responses or generated for the session
    /// </summary>
    public long? AccountId { get; set; }
    
    /// <summary>
    /// Player nickname captured from official responses or generated for the session
    /// </summary>
    public string? Nickname { get; set; }
    
    /// <summary>
    /// Player call name captured from official responses or generated for the session
    /// </summary>
    public string? CallName { get; set; }
    
    /// <summary>
    /// Player level captured from official responses or generated for the session
    /// </summary>
    public int? Level { get; set; }
    
    /// <summary>
    /// Player experience captured from official responses or generated for the session
    /// </summary>
    public long? Exp { get; set; }
    
    /// <summary>
    /// Representative character ID captured from official responses or generated for the session
    /// </summary>
    public long? RepresentCharacterUniqueId { get; set; }
    
    /// <summary>
    /// Player comment captured from official responses or generated for the session
    /// </summary>
    public string? Comment { get; set; }
    
    /// <summary>
    /// Friend code captured from official responses or generated for the session
    /// </summary>
    public string? FriendCode { get; set; }
    
    /// <summary>
    /// Session creation timestamp
    /// </summary>
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Last access timestamp
    /// </summary>
    public DateTime LastAccessedAt { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Additional dynamic session data captured from official server responses
    /// </summary>
    public Dictionary<string, object> Data { get; set; } = new();
    
    /// <summary>
    /// Session cookies captured from requests (AWSALB, AWSALBCORS, etc.)
    /// </summary>
    public Dictionary<string, string> Cookies { get; set; } = new();
    
    /// <summary>
    /// Tracks whether this session has been initialized from an official server capture
    /// </summary>
    public bool IsOfficialCapture { get; set; } = false;
    
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
    /// Captures session data from an official server response
    /// </summary>
    /// <param name="responseData">Response data object from official server</param>
    public void CaptureOfficialData(object responseData)
    {
        if (responseData == null) return;
        
        try
        {
            // Use reflection to capture common fields from any response object
            var type = responseData.GetType();
            var properties = type.GetProperties();
            
            foreach (var prop in properties)
            {
                var value = prop.GetValue(responseData);
                if (value == null) continue;
                
                switch (prop.Name.ToLower())
                {
                    case "accountid":
                        if (AccountId == null && long.TryParse(value.ToString(), out var accId))
                            AccountId = accId;
                        break;
                    case "accountserverid":
                        if (AccountServerId == null && int.TryParse(value.ToString(), out var serverId))
                            AccountServerId = serverId;
                        break;
                    case "nickname":
                        if (string.IsNullOrEmpty(Nickname))
                            Nickname = value.ToString();
                        break;
                    case "callname":
                        if (string.IsNullOrEmpty(CallName))
                            CallName = value.ToString();
                        break;
                    case "level":
                        if (Level == null && int.TryParse(value.ToString(), out var level))
                            Level = level;
                        break;
                    case "exp":
                        if (Exp == null && long.TryParse(value.ToString(), out var exp))
                            Exp = exp;
                        break;
                    case "representcharacteruniqueid":
                        if (RepresentCharacterUniqueId == null && long.TryParse(value.ToString(), out var charId))
                            RepresentCharacterUniqueId = charId;
                        break;
                    case "comment":
                        if (string.IsNullOrEmpty(Comment))
                            Comment = value.ToString();
                        break;
                    case "friendcode":
                        if (string.IsNullOrEmpty(FriendCode))
                            FriendCode = value.ToString();
                        break;
                }
            }
            
            IsOfficialCapture = true;
        }
        catch (Exception)
        {
            // Ignore reflection errors, this is best-effort data capture
        }
    }
    
    /// <summary>
    /// Generates reasonable default values for a session that hasn't been captured from official server
    /// </summary>
    public void GenerateDefaultsIfMissing()
    {
        var random = new Random(SessionId.GetHashCode()); // Deterministic based on session ID
        
        if (AccountId == null)
            AccountId = 1000000 + random.Next(1, 999999); // Generate ID in reasonable range
            
        if (AccountServerId == null)
            AccountServerId = random.Next(1, 10); // Server 1-10
            
        if (string.IsNullOrEmpty(Nickname))
            Nickname = $"Player{AccountId % 10000:D4}";
            
        if (string.IsNullOrEmpty(CallName))
            CallName = Nickname; // Use same as nickname by default
            
        if (Level == null)
            Level = random.Next(1, 80); // Random level 1-80
            
        if (Exp == null)
            Exp = Level * 1000 + random.Next(0, 999); // Reasonable exp for level
            
        if (RepresentCharacterUniqueId == null)
            RepresentCharacterUniqueId = 10000 + random.Next(1, 50); // Common character IDs
            
        if (string.IsNullOrEmpty(Comment))
            Comment = "Generated session data";
            
        if (string.IsNullOrEmpty(FriendCode))
        {
            // Generate a 12-digit friend code
            var code = random.Next(100000, 999999).ToString() + random.Next(100000, 999999).ToString();
            FriendCode = code;
        }
    }
    
    /// <summary>
    /// Gets the consistent AccountId for this session (generates if needed)
    /// </summary>
    public long GetAccountId()
    {
        if (AccountId == null)
        {
            GenerateDefaultsIfMissing();
        }
        return AccountId!.Value;
    }
    
    /// <summary>
    /// Gets the consistent AccountServerId for this session (generates if needed)
    /// </summary>
    public int GetAccountServerId()
    {
        if (AccountServerId == null)
        {
            GenerateDefaultsIfMissing();
        }
        return AccountServerId!.Value;
    }
    
    /// <summary>
    /// Gets the consistent Nickname for this session (generates if needed)
    /// </summary>
    public string GetNickname()
    {
        if (string.IsNullOrEmpty(Nickname))
        {
            GenerateDefaultsIfMissing();
        }
        return Nickname!;
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