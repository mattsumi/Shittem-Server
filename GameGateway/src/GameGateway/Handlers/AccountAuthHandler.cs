using GameGateway.Interfaces;
using GameGateway.Models;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace GameGateway.Handlers;

/// <summary>
/// Handler for Account_Auth protocol (main authentication)
/// </summary>
public class AccountAuthHandler : IProtocolHandler
{
    private readonly IConfiguration _configuration;
    private readonly ILogger<AccountAuthHandler> _logger;

    public string ProtocolName => "Account_Auth";
    public int? ProtocolCode => 10003; // Example numeric code

    public AccountAuthHandler(IConfiguration configuration, ILogger<AccountAuthHandler> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<object> HandleAsync(
        GameRequest request, 
        GameSession session, 
        string requestId, 
        CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Processing Account_Auth request {RequestId} for session {SessionId}", 
            requestId, session.SessionId);

        try
        {
            // Extract authentication data from request
            string? requestMxToken = null;
            string? deviceId = null;
            string? version = null;

            if (request.Payload.HasValue)
            {
                try
                {
                    var packetJson = request.Payload.Value.GetRawText();
                    var packetData = JsonSerializer.Deserialize<JsonElement>(packetJson);
                    
                    if (packetData.TryGetProperty("MxToken", out var mxTokenElement))
                    {
                        requestMxToken = mxTokenElement.GetString();
                    }

                    if (packetData.TryGetProperty("DeviceId", out var deviceElement))
                    {
                        deviceId = deviceElement.GetString();
                    }

                    if (packetData.TryGetProperty("Version", out var versionElement))
                    {
                        version = versionElement.GetString();
                    }

                    _logger.LogDebug("Account_Auth request {RequestId} - DeviceId: {DeviceId}, Version: {Version}", 
                        requestId, deviceId?[..Math.Min(8, deviceId.Length)] + "...", version);
                }
                catch (Exception ex)
                {
                    _logger.LogDebug(ex, "Could not parse authentication data from Account_Auth packet in request {RequestId}", requestId);
                }
            }

            // Capture or get the session's MxToken
            var sessionMxToken = session.CaptureOrGetMxToken(requestMxToken);
            
            // Set default values if not already set
            if (!session.AccountServerId.HasValue)
            {
                session.AccountServerId = 1; // Default server
            }

            if (!session.AccountId.HasValue)
            {
                // Generate a deterministic account ID based on session ID
                var sessionBytes = System.Text.Encoding.UTF8.GetBytes(session.SessionId);
                var hash = System.Security.Cryptography.MD5.HashData(sessionBytes);
                session.AccountId = BitConverter.ToInt64(hash, 0) & 0x7FFFFFFFFFFFFFFF; // Ensure positive
            }

            // Generate auth token based on session
            var authTokenBytes = System.Text.Encoding.UTF8.GetBytes($"{session.SessionId}:{sessionMxToken}:{DateTime.UtcNow:yyyy-MM-dd}");
            var authTokenHash = System.Security.Cryptography.SHA256.HashData(authTokenBytes);
            var authToken = Convert.ToBase64String(authTokenHash)[..32]; // Take first 32 chars

            var response = new AccountAuthResponse
            {
                Protocol = ProtocolCode ?? 10003,
                ResultState = 1, // Success
                ServerTimeTicks = DateTime.UtcNow.Ticks,
                SessionKey = new SessionKeyInfo
                {
                    AccountServerId = session.AccountServerId,
                    MxToken = sessionMxToken
                },
                AccountId = session.AccountId.Value,
                AuthToken = authToken,
                AccountInfo = new AccountInfo
                {
                    AccountId = session.AccountId.Value,
                    AccountServerId = session.AccountServerId.Value,
                    Nickname = $"Player_{session.SessionId[..8]}",
                    Level = 1,
                    Experience = 0,
                    LastLoginTime = DateTime.UtcNow.Ticks
                }
            };

            _logger.LogInformation("Account_Auth completed for request {RequestId}: AccountId={AccountId}, ServerId={ServerId}, AuthToken={AuthToken}", 
                requestId, session.AccountId, session.AccountServerId, authToken[..8] + "...");

            return response;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to process Account_Auth request {RequestId}", requestId);
            throw;
        }
    }
}

/// <summary>
/// Response payload for Account_Auth
/// </summary>
public class AccountAuthResponse : BaseResponsePayload
{
    /// <summary>
    /// Result state of the authentication
    /// </summary>
    [JsonPropertyName("ResultState")]
    public int ResultState { get; set; }

    /// <summary>
    /// Session key information
    /// </summary>
    [JsonPropertyName("SessionKey")]
    public SessionKeyInfo SessionKey { get; set; } = new();

    /// <summary>
    /// Account ID
    /// </summary>
    [JsonPropertyName("AccountId")]
    public long AccountId { get; set; }

    /// <summary>
    /// Authentication token
    /// </summary>
    [JsonPropertyName("AuthToken")]
    public string AuthToken { get; set; } = string.Empty;

    /// <summary>
    /// Account information
    /// </summary>
    [JsonPropertyName("AccountInfo")]
    public AccountInfo AccountInfo { get; set; } = new();
}

/// <summary>
/// Account information details
/// </summary>
public class AccountInfo
{
    /// <summary>
    /// Account ID
    /// </summary>
    [JsonPropertyName("AccountId")]
    public long AccountId { get; set; }

    /// <summary>
    /// Account server ID
    /// </summary>
    [JsonPropertyName("AccountServerId")]
    public long AccountServerId { get; set; }

    /// <summary>
    /// Player nickname
    /// </summary>
    [JsonPropertyName("Nickname")]
    public string Nickname { get; set; } = string.Empty;

    /// <summary>
    /// Player level
    /// </summary>
    [JsonPropertyName("Level")]
    public int Level { get; set; }

    /// <summary>
    /// Player experience points
    /// </summary>
    [JsonPropertyName("Experience")]
    public long Experience { get; set; }

    /// <summary>
    /// Last login timestamp
    /// </summary>
    [JsonPropertyName("LastLoginTime")]
    public long LastLoginTime { get; set; }
}