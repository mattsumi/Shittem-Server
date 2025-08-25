using GameGateway.Interfaces;
using GameGateway.Models;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace GameGateway.Handlers;

/// <summary>
/// Handler for Account_Check protocol (first auth probe)
/// </summary>
public class AccountCheckHandler : IProtocolHandler
{
    private readonly IConfiguration _configuration;
    private readonly ILogger<AccountCheckHandler> _logger;

    public string ProtocolName => "Account_Check";
    public int? ProtocolCode => 10002; // Example numeric code

    public AccountCheckHandler(IConfiguration configuration, ILogger<AccountCheckHandler> logger)
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
        _logger.LogInformation("Processing Account_Check request {RequestId} for session {SessionId}", 
            requestId, session.SessionId);

        try
        {
            // Extract MxToken from request if present
            string? requestMxToken = null;
            if (request.Payload.HasValue)
            {
                try
                {
                    var packetJson = request.Payload.Value.GetRawText();
                    var packetData = JsonSerializer.Deserialize<JsonElement>(packetJson);
                    
                    if (packetData.TryGetProperty("MxToken", out var mxTokenElement))
                    {
                        requestMxToken = mxTokenElement.GetString();
                        _logger.LogDebug("Found MxToken in Account_Check request {RequestId}: {MxToken}", 
                            requestId, requestMxToken?[..Math.Min(8, requestMxToken.Length)] + "...");
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogDebug(ex, "Could not parse MxToken from Account_Check packet in request {RequestId}", requestId);
                }
            }

            // Capture or get the session's MxToken
            var sessionMxToken = session.CaptureOrGetMxToken(requestMxToken);
            
            // Set default account server ID if not already set
            if (!session.AccountServerId.HasValue)
            {
                session.AccountServerId = 1; // Default server
            }

            // Set default account ID if not already set
            if (!session.AccountId.HasValue)
            {
                // Generate a deterministic account ID based on session ID
                var sessionBytes = System.Text.Encoding.UTF8.GetBytes(session.SessionId);
                var hash = System.Security.Cryptography.MD5.HashData(sessionBytes);
                session.AccountId = BitConverter.ToInt64(hash, 0) & 0x7FFFFFFFFFFFFFFF; // Ensure positive
            }

            var response = new AccountCheckResponse
            {
                Protocol = ProtocolCode ?? 10002,
                ResultState = 1, // Success
                ServerTimeTicks = DateTime.UtcNow.Ticks,
                SessionKey = new SessionKeyInfo
                {
                    AccountServerId = session.AccountServerId,
                    MxToken = sessionMxToken
                },
                AccountId = session.AccountId.Value
            };

            _logger.LogInformation("Account_Check completed for request {RequestId}: AccountId={AccountId}, ServerId={ServerId}", 
                requestId, session.AccountId, session.AccountServerId);

            return response;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to process Account_Check request {RequestId}", requestId);
            throw;
        }
    }
}

/// <summary>
/// Response payload for Account_Check
/// </summary>
public class AccountCheckResponse : BaseResponsePayload
{
    /// <summary>
    /// Result state of the check
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
}