using System.Text.Json;
using System.Text.Json.Serialization;

namespace GameGateway.Models;

/// <summary>
/// Represents a decoded game request
/// </summary>
public class GameRequest
{
    /// <summary>
    /// Protocol name (string format)
    /// </summary>
    [JsonPropertyName("Protocol")]
    public string? Protocol { get; set; }
    
    /// <summary>
    /// Protocol code (numeric format, alternative to Protocol)
    /// </summary>
    [JsonPropertyName("protocol_code")]
    public int? ProtocolCode { get; set; }
    
    /// <summary>
    /// The packet data containing the request payload
    /// </summary>
    [JsonPropertyName("Payload")]
    public JsonElement? Payload { get; set; }
    
    /// <summary>
    /// Request ID for correlation
    /// </summary>
    [JsonPropertyName("RequestId")]
    public string? RequestId { get; set; }
    
    /// <summary>
    /// Additional fields from the request
    /// </summary>
    [JsonExtensionData]
    public Dictionary<string, JsonElement>? AdditionalData { get; set; }
    
    /// <summary>
    /// Gets the effective protocol identifier (string or numeric)
    /// </summary>
    public object GetProtocolIdentifier() => Protocol ?? (object?)ProtocolCode ?? string.Empty;
}