using System.Text.Json.Serialization;

namespace GameGateway.Models;

/// <summary>
/// Represents a game response that will be sent back to the client
/// </summary>
public class GameResponse
{
    /// <summary>
    /// Protocol code (numeric identifier)
    /// </summary>
    [JsonPropertyName("protocol")]
    public int Protocol { get; set; }
    
    /// <summary>
    /// Result state of the operation
    /// </summary>
    [JsonPropertyName("resultState")]
    public int ResultState { get; set; }
    
    /// <summary>
    /// Server time ticks
    /// </summary>
    [JsonPropertyName("serverTimeTicks")]
    public long ServerTimeTicks { get; set; }
    
    /// <summary>
    /// The response payload object
    /// </summary>
    [JsonPropertyName("payload")]
    public object? Payload { get; set; }
}

/// <summary>
/// Base class for protocol-specific response payloads
/// </summary>
public abstract class BaseResponsePayload
{
    /// <summary>
    /// Numeric protocol code
    /// </summary>
    [JsonPropertyName("Protocol")]
    public int Protocol { get; set; }
    
    /// <summary>
    /// Server time ticks (DateTime.UtcNow.Ticks)
    /// </summary>
    [JsonPropertyName("ServerTimeTicks")]
    public long ServerTimeTicks { get; set; } = DateTime.UtcNow.Ticks;
}

/// <summary>
/// Session key information included in responses
/// </summary>
public class SessionKeyInfo
{
    /// <summary>
    /// Account server ID
    /// </summary>
    [JsonPropertyName("AccountServerId")]
    public int? AccountServerId { get; set; }
    
    /// <summary>
    /// The consistent MxToken for this session
    /// </summary>
    [JsonPropertyName("MxToken")]
    public string? MxToken { get; set; }
}

/// <summary>
/// Minimal account database information
/// </summary>
public class AccountDB
{
    /// <summary>
    /// Server ID
    /// </summary>
    [JsonPropertyName("ServerId")]
    public int ServerId { get; set; }
    
    /// <summary>
    /// Player nickname
    /// </summary>
    [JsonPropertyName("Nickname")]
    public string Nickname { get; set; } = "TestPlayer";
    
    /// <summary>
    /// Account state
    /// </summary>
    [JsonPropertyName("State")]
    public int State { get; set; } = 1;
    
    /// <summary>
    /// Player level
    /// </summary>
    [JsonPropertyName("Level")]
    public int Level { get; set; } = 1;
}