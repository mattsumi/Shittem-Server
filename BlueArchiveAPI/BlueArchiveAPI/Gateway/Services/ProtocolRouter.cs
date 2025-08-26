using BlueArchiveAPI.Gateway.Models;
using BlueArchiveAPI.Gateway.Interfaces;
using BlueArchiveAPI.NetworkModels;
using BlueArchiveAPI.Handlers;
using BlueArchiveAPI.Models;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using BlueArchiveAPI.Admin;

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
                handlerName = request.Protocol ?? "Unknown";
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
            var packetString = await PreparePacketForHandler(request, session, handlerName ?? "Unknown");
            var response = await handler.Handle(packetString);
            
            var duration = DateTime.UtcNow - startTime;
            _logger.LogInformation("Handler {HandlerName} completed request {RequestId} in {Duration}ms",
                handlerName, requestId, duration.TotalMilliseconds);

            // Parse the response bytes back to JSON object
            var responseJson = System.Text.Encoding.UTF8.GetString(response);
            var serverPacket = JsonConvert.DeserializeObject<BlueArchiveAPI.Models.ServerPacket>(responseJson);
            if (serverPacket == null || string.IsNullOrWhiteSpace(serverPacket.Packet))
            {
                throw new InvalidOperationException("Invalid server packet format returned by handler");
            }
            
            // Parse the inner packet as object for session data capture
            var responseObject = JsonConvert.DeserializeObject(serverPacket.Packet) ?? new object();
            
            // Capture dynamic session data from the response (best effort)
            await CaptureSessionDataFromResponse(session, responseObject, handlerName, requestId);
            
            // Return the response object
            return responseObject;
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
            var payloadJson = request.Payload.HasValue ? request.Payload.Value.GetRawText() : "{}";
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

            // Set AccountServerId from session (generates defaults if needed)
            if (sessionKeyToken["AccountServerId"] == null)
            {
                sessionKeyToken["AccountServerId"] = session.GetAccountServerId();
            }

            // Update the packet with the enriched SessionKey
            packetData["SessionKey"] = sessionKeyToken;

            // Ensure AccountId is present at the root level (required by BasePacket)
            if (packetData["AccountId"] == null)
            {
                packetData["AccountId"] = session.GetAccountId();
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
            if (request.Payload.HasValue)
            {
                try
                {
                    var payloadObj = JObject.Parse(request.Payload.Value.GetRawText());
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
                ["AccountServerId"] = session.GetAccountServerId(),
                ["MxToken"] = session.CaptureOrGetMxToken()
            };
            fallbackPacket["AccountId"] = session.GetAccountId();

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
    
    /// <summary>
    /// Captures session data from handler responses to maintain consistency
    /// </summary>
    /// <param name="session">Game session to update</param>
    /// <param name="responseObject">Response data from handler</param>
    /// <param name="protocolName">Protocol name for logging</param>
    /// <param name="requestId">Request correlation ID</param>
    private async Task CaptureSessionDataFromResponse(GameSession session, object responseObject, string protocolName, string requestId)
    {
        if (responseObject == null) return;
        
        try
        {
            // Key protocols that contain user account data
            var shouldCapture = protocolName.StartsWith("Account_") ||
                               protocolName.Contains("Auth") ||
                               protocolName.Contains("Login") ||
                               protocolName.Contains("Check");
            
            if (shouldCapture)
            {
                // Capture data using the GameSession's reflection-based capture method
                session.CaptureOfficialData(responseObject);
                
                // Also look for nested account data in common response structures
                if (responseObject is JObject jobj)
                {
                    // Look for UserDB or AccountDB objects
                    var userDb = jobj.SelectToken("UserDB") ?? jobj.SelectToken("AccountDB");
                    if (userDb != null)
                    {
                        var userDbObj = userDb.ToObject<object>();
                        if (userDbObj != null)
                        {
                            session.CaptureOfficialData(userDbObj);
                        }
                    }
                    
                    // Look for SessionKey data
                    var sessionKey = jobj.SelectToken("SessionKey");
                    if (sessionKey != null)
                    {
                        var sessionKeyObj = sessionKey.ToObject<object>();
                        if (sessionKeyObj != null)
                        {
                            session.CaptureOfficialData(sessionKeyObj);
                        }
                        
                        // Specifically capture MxToken if present
                        var mxToken = sessionKey.SelectToken("MxToken")?.ToString();
                        if (!string.IsNullOrEmpty(mxToken))
                        {
                            session.CaptureOrGetMxToken(mxToken);
                        }
                    }

                    // NEW: Persist captured account data to AdminStore for immediate admin API access
                    await PersistAccountDataToAdminStore(jobj, session, protocolName);
                }
                
                _logger.LogDebug("Captured session data from {Protocol} response for request {RequestId} (Official: {IsOfficial})",
                    protocolName, requestId, session.IsOfficialCapture);
            }
            
            // For sessions without captured data, ensure defaults are generated
            if (!session.IsOfficialCapture)
            {
                session.GenerateDefaultsIfMissing();
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to capture session data from {Protocol} response for request {RequestId}",
                protocolName, requestId);
        }
        
        await Task.CompletedTask;
    }

    /// <summary>
    /// Extracts authoritative account data from Account_Check, Account_Auth, and post-login responses
    /// and persists to AdminStore using the new AccountSnapshot model
    /// </summary>
    /// <param name="responseObject">JSON response object from protocol</param>
    /// <param name="session">Current game session</param>
    /// <param name="protocolName">Protocol name for logging</param>
    private async Task PersistAccountDataToAdminStore(JObject responseObject, GameSession session, string protocolName)
    {
        try
        {
            var adminStore = _serviceProvider.GetService<BlueArchiveAPI.Admin.IAdminStore>();
            if (adminStore == null)
            {
                _logger.LogWarning("AdminStore service not available for data persistence from {Protocol}", protocolName);
                return;
            }

            var accountId = session.GetAccountId();
            if (accountId <= 0)
            {
                _logger.LogWarning("Invalid AccountId {AccountId} for AdminStore persistence from {Protocol}", accountId, protocolName);
                return;
            }

            // Only capture from specific authoritative protocols
            var isAuthoritative = protocolName.Equals("Account_Check", StringComparison.OrdinalIgnoreCase) ||
                                  protocolName.Equals("Account_Auth", StringComparison.OrdinalIgnoreCase) ||
                                  protocolName.Contains("Login", StringComparison.OrdinalIgnoreCase);

            if (!isAuthoritative)
            {
                _logger.LogDebug("Skipping account data capture from non-authoritative protocol {Protocol}", protocolName);
                return;
            }

            // Create snapshot from official response data
            var snapshot = new AccountSnapshot
            {
                AccountId = accountId,
                UpdatedAt = DateTimeOffset.UtcNow
            };

            var hasData = false;

            // Helper function to extract value from multiple JSON paths
            T? TryExtractValue<T>(params string[] jsonPaths) where T : struct
            {
                foreach (var path in jsonPaths)
                {
                    var token = responseObject.SelectToken(path);
                    if (token?.Type != JTokenType.Null && token?.Value<T?>() is T value)
                    {
                        return value;
                    }
                }
                return null;
            }

            string? TryExtractString(params string[] jsonPaths)
            {
                foreach (var path in jsonPaths)
                {
                    var token = responseObject.SelectToken(path);
                    var value = token?.ToString();
                    if (!string.IsNullOrEmpty(value) && value != "null")
                    {
                        return value;
                    }
                }
                return null;
            }

            // Extract authoritative account fields from various possible locations
            snapshot.Nickname = TryExtractString(
                "Nickname", "UserDB.Nickname", "AccountDB.Nickname",
                "User.Nickname", "Account.Nickname", "PlayerDB.Nickname");

            snapshot.Level = TryExtractValue<int>(
                "Level", "UserDB.Level", "AccountDB.Level",
                "User.Level", "Account.Level", "PlayerDB.Level");

            // Try to get separate paid/free pyroxene first, then combined
            snapshot.PaidPyroxene = TryExtractValue<int>(
                "PaidPyroxene", "UserDB.PaidPyroxene", "AccountDB.PaidPyroxene",
                "Currency.PaidPyroxene", "Pyroxene.Paid");

            snapshot.FreePyroxene = TryExtractValue<int>(
                "FreePyroxene", "UserDB.FreePyroxene", "AccountDB.FreePyroxene",
                "Currency.FreePyroxene", "Pyroxene.Free");

            // If separate values not found, try combined pyroxene
            if (!snapshot.PaidPyroxene.HasValue && !snapshot.FreePyroxene.HasValue)
            {
                snapshot.Pyroxene = TryExtractValue<int>(
                    "Pyroxene", "UserDB.Pyroxene", "AccountDB.Pyroxene",
                    "User.Pyroxene", "Account.Pyroxene", "Currency.Pyroxene");
            }

            snapshot.Credits = TryExtractValue<int>(
                "Credits", "UserDB.Credits", "AccountDB.Credits",
                "User.Credits", "Account.Credits", "Currency.Credits");

            // Check if we captured any meaningful data
            hasData = !string.IsNullOrEmpty(snapshot.Nickname) ||
                      snapshot.Level.HasValue ||
                      snapshot.Pyroxene.HasValue ||
                      snapshot.PaidPyroxene.HasValue ||
                      snapshot.FreePyroxene.HasValue ||
                      snapshot.Credits.HasValue;

            // Fallback: try to get data from session if response didn't contain it
            if (!hasData && session.IsOfficialCapture)
            {
                if (!string.IsNullOrEmpty(session.Nickname))
                {
                    snapshot.Nickname = session.Nickname;
                    hasData = true;
                }
                if (session.Level.HasValue)
                {
                    snapshot.Level = session.Level.Value;
                    hasData = true;
                }
            }

            // Persist the snapshot if we captured authoritative data
            if (hasData)
            {
                await adminStore.SaveAsync(snapshot);
                _logger.LogInformation("Captured authoritative account data from {Protocol} for AccountId {AccountId}: " +
                    "Nickname={Nickname}, Level={Level}, Pyroxene={Pyroxene}, Credits={Credits}",
                    protocolName, accountId, snapshot.Nickname, snapshot.Level,
                    snapshot.Pyroxene ?? (snapshot.PaidPyroxene + snapshot.FreePyroxene), snapshot.Credits);
            }
            else
            {
                _logger.LogDebug("No authoritative account data found in {Protocol} response for AccountId {AccountId}",
                    protocolName, accountId);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to capture account data from {Protocol} for AdminStore", protocolName);
        }

        await Task.CompletedTask;
    }
}