using BlueArchiveAPI.Gateway.Interfaces;
using BlueArchiveAPI.Gateway.Models;
using BlueArchiveAPI.NetworkModels;
using BlueArchiveAPI.Handlers;
using BlueArchiveAPI.Models;
using System.Text.Json;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BlueArchiveAPI.Gateway.Services;

/// <summary>
/// Routes protocol requests to appropriate handlers using existing HandlerManager
/// </summary>
public class ProtocolRouter
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<ProtocolRouter> _logger;

    public ProtocolRouter(IServiceProvider serviceProvider, ILogger<ProtocolRouter> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    /// <summary>
    /// Routes a request to the appropriate protocol handler using existing HandlerManager
    /// </summary>
    /// <param name="request">The decoded game request</param>
    /// <param name="session">The game session</param>
    /// <param name="requestId">Request correlation ID</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>The response payload from the handler</returns>
    public async Task<object> RouteAsync(
        GameRequest request,
        GameSession session,
        string requestId,
        CancellationToken cancellationToken = default)
    {
        return await RouteRequestAsync(request, session, requestId, cancellationToken);
    }

    /// <summary>
    /// Routes a request to the appropriate protocol handler using existing HandlerManager
    /// </summary>
    /// <param name="request">The decoded game request</param>
    /// <param name="session">The game session</param>
    /// <param name="requestId">Request correlation ID</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>The response payload from the handler</returns>
    public async Task<object> RouteRequestAsync(
        GameRequest request,
        GameSession session,
        string requestId,
        CancellationToken cancellationToken = default)
    {
        IHandler? handler = null;
        string handlerName = "Unknown";
        Protocol? protocolEnum = null;

        try
        {
            // Try to resolve Protocol enum from string name or numeric code
            if (!string.IsNullOrEmpty(request.Protocol))
            {
                protocolEnum = Utils.ParseProtocolString(request.Protocol);
                handlerName = request.Protocol;
            }
            else if (request.ProtocolCode.HasValue)
            {
                if (Enum.IsDefined(typeof(Protocol), request.ProtocolCode.Value))
                {
                    protocolEnum = (Protocol)request.ProtocolCode.Value;
                    handlerName = protocolEnum.ToString();
                }
            }

            // Get handler from HandlerManager using Protocol enum
            if (protocolEnum.HasValue)
            {
                handler = HandlerManager.GetHandler(protocolEnum.Value);
            }

            if (handler == null)
            {
                var protocolId = request.GetProtocolIdentifier();
                _logger.LogWarning("No handler found for protocol: {Protocol} in request {RequestId}",
                    protocolId, requestId);
                    
                throw new InvalidOperationException($"No handler registered for protocol: {protocolId}");
            }

            _logger.LogDebug("Routing request {RequestId} to handler {HandlerName} ({HandlerType})",
                requestId, handlerName, handler.GetType().Name);

            var startTime = DateTime.UtcNow;
            
            // Convert request payload to packet string format expected by existing handlers
            // This includes SessionKey enrichment and proper encryption
            var packetString = await PreparePacketForHandler(request, session, handlerName);
            var response = await handler.Handle(packetString);
            
            var duration = DateTime.UtcNow - startTime;
            _logger.LogInformation("Handler {HandlerName} completed request {RequestId} in {Duration}ms",
                handlerName, requestId, duration.TotalMilliseconds);

            // Parse the response bytes back to JSON object
            var responseJson = System.Text.Encoding.UTF8.GetString(response);
            var serverPacket = JsonConvert.DeserializeObject<ServerPacket>(responseJson);
            
            // Return the inner packet as parsed JSON object
            return JsonConvert.DeserializeObject(serverPacket.Packet);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Handler {HandlerName} failed for request {RequestId}", handlerName, requestId);
            throw;
        }
    }

    /// <summary>
    /// Gets the list of registered protocol handlers for diagnostics
    /// </summary>
    /// <returns>Dictionary of protocol names/codes to handler types</returns>
    public Dictionary<string, string> GetRegisteredHandlers()
    {
        var handlers = new Dictionary<string, string>();
        
        // Get all Protocol enum values and check if they have handlers
        foreach (Protocol protocol in Enum.GetValues<Protocol>())
        {
            var handler = HandlerManager.GetHandler(protocol);
            if (handler != null)
            {
                handlers[$"enum:{protocol}"] = handler.GetType().Name;
                handlers[$"string:{protocol}"] = handler.GetType().Name;
                handlers[$"numeric:{(int)protocol}"] = handler.GetType().Name;
            }
        }
        
        return handlers;
    }

    /// <summary>
    /// Checks if a handler exists for the given protocol
    /// </summary>
    /// <param name="protocol">Protocol name</param>
    /// <param name="protocolCode">Protocol code</param>
    /// <returns>True if a handler exists</returns>
    public bool HasHandler(string? protocol, int? protocolCode)
    {
        if (!string.IsNullOrEmpty(protocol))
        {
            var protocolEnum = Utils.ParseProtocolString(protocol);
            if (protocolEnum.HasValue && HandlerManager.GetHandler(protocolEnum.Value) != null)
                return true;
        }
            
        if (protocolCode.HasValue && Enum.IsDefined(typeof(Protocol), protocolCode.Value))
        {
            var protocolEnum = (Protocol)protocolCode.Value;
            if (HandlerManager.GetHandler(protocolEnum) != null)
                return true;
        }
            
        return false;
    }

    /// <summary>
    /// Gets the protocol string name from the Protocol enum
    /// </summary>
    /// <param name="protocolCode">Numeric protocol code</param>
    /// <returns>Protocol string name or null if not found</returns>
    public static string? GetProtocolName(int protocolCode)
    {
        if (Enum.IsDefined(typeof(Protocol), protocolCode))
        {
            return ((Protocol)protocolCode).ToString();
        }
        return null;
    }

    /// <summary>
    /// Gets the protocol code from the Protocol enum
    /// </summary>
    /// <param name="protocolName">Protocol string name</param>
    /// <returns>Protocol numeric code or null if not found</returns>
    public static int? GetProtocolCode(string protocolName)
    {
        var protocolEnum = Utils.ParseProtocolString(protocolName);
        return protocolEnum.HasValue ? (int)protocolEnum.Value : null;
    }

    /// <summary>
    /// Prepares the request packet for handler processing with SessionKey enrichment and proper encryption
    /// </summary>
    /// <param name="request">The incoming Gateway request</param>
    /// <param name="session">The game session</param>
    /// <param name="protocolName">Protocol name for logging</param>
    /// <returns>Encrypted packet string in format expected by existing handlers</returns>
    private async Task<string> PreparePacketForHandler(GameRequest request, GameSession session, string protocolName)
    {
        try
        {
            // Start with the payload JSON from the Gateway request
            var payloadJson = request.Payload?.ToString() ?? "{}";
            var packetData = JObject.Parse(payloadJson);

            // Extract MxToken from the request if present (for token capture)
            var incomingMxToken = packetData.SelectToken("SessionKey.MxToken")?.ToString();
            if (!string.IsNullOrEmpty(incomingMxToken))
            {
                // Capture the token in our session
                session.CaptureOrGetMxToken(incomingMxToken);
                _logger.LogDebug("Captured MxToken from {Protocol} request", protocolName);
            }

            // Ensure SessionKey is properly populated in the packet
            var sessionKeyToken = packetData["SessionKey"] as JObject ?? new JObject();

            // Use existing session MxToken or set empty if none captured yet
            var currentMxToken = session.CaptureOrGetMxToken();
            sessionKeyToken["MxToken"] = currentMxToken;

            // Set AccountServerId from session (or default for new sessions)
            if (sessionKeyToken["AccountServerId"] == null)
            {
                // For new sessions, we might not have an AccountServerId yet
                // Some handlers (like Account.CheckNexon) will set this
                sessionKeyToken["AccountServerId"] = session.AccountId ?? 0;
            }

            // Update the packet with the enriched SessionKey
            packetData["SessionKey"] = sessionKeyToken;

            // Ensure AccountId is present at the root level (required by BasePacket)
            if (packetData["AccountId"] == null)
            {
                packetData["AccountId"] = session.AccountId ?? 0;
            }

            _logger.LogDebug("Enriched {Protocol} packet with SessionKey (AccountServerId: {AccountId}, MxToken: {HasToken})",
                protocolName, sessionKeyToken["AccountServerId"], !string.IsNullOrEmpty(currentMxToken));

            // Convert back to the encrypted packet format that existing handlers expect
            var enrichedJson = packetData.ToString(Formatting.None);
            var enrichedBytes = System.Text.Encoding.UTF8.GetBytes(enrichedJson);
            var compressed = Utils.GZipCompress(enrichedBytes);
            var packetSize = BitConverter.GetBytes(enrichedBytes.Length);
            var finalPacket = new byte[packetSize.Length + compressed.Length];
            Array.Copy(packetSize, finalPacket, packetSize.Length);
            Array.Copy(compressed, 0, finalPacket, packetSize.Length, compressed.Length);

            return Convert.ToBase64String(finalPacket);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to enrich request with SessionKey for {Protocol}, using basic format", protocolName);
            
            // Fallback: create a basic packet with minimal SessionKey
            var fallbackPacket = new JObject();
            if (request.Payload != null)
            {
                try
                {
                    var payloadObj = JObject.Parse(request.Payload.ToString());
                    foreach (var prop in payloadObj.Properties())
                    {
                        fallbackPacket[prop.Name] = prop.Value;
                    }
                }
                catch
                {
                    // If payload parsing fails, start with empty object
                }
            }

            // Add minimal SessionKey
            fallbackPacket["SessionKey"] = new JObject
            {
                ["AccountServerId"] = session.AccountId ?? 0,
                ["MxToken"] = session.CaptureOrGetMxToken()
            };
            fallbackPacket["AccountId"] = session.AccountId ?? 0;

            // Format as encrypted packet
            var json = fallbackPacket.ToString(Formatting.None);
            var bytes = System.Text.Encoding.UTF8.GetBytes(json);
            var compressed = Utils.GZipCompress(bytes);
            var packetSize = BitConverter.GetBytes(bytes.Length);
            var packet = new byte[packetSize.Length + compressed.Length];
            Array.Copy(packetSize, packet, packetSize.Length);
            Array.Copy(compressed, 0, packet, packetSize.Length, compressed.Length);

            return Convert.ToBase64String(packet);
        }
    }
}