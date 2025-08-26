using BlueArchiveAPI.Gateway.Models;
using BlueArchiveAPI.Gateway.Services;
using BlueArchiveAPI.Models;
using BlueArchiveAPI.NetworkModels;
using Microsoft.AspNetCore.Mvc;
using Newtonsoft.Json;
using System.Text;
using System.Text.Json;

namespace BlueArchiveAPI.Controllers;

/// <summary>
/// Gateway controller that handles game protocol requests with multipart/form-data parsing,
/// codec pipeline support, and session management
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class GatewayController : ControllerBase
{
    private readonly ILogger<GatewayController> _logger;
    private readonly MultipartParser _multipartParser;
    private readonly CodecRegistry _codecRegistry;
    private readonly ProtocolRouter _protocolRouter;
    private readonly SessionManager _sessionManager;

    public GatewayController(
        ILogger<GatewayController> logger,
        MultipartParser multipartParser,
        CodecRegistry codecRegistry,
        ProtocolRouter protocolRouter,
        SessionManager sessionManager)
    {
        _logger = logger;
        _multipartParser = multipartParser;
        _codecRegistry = codecRegistry;
        _protocolRouter = protocolRouter;
        _sessionManager = sessionManager;
    }

    /// <summary>
    /// Main gateway endpoint that handles all game protocol requests
    /// </summary>
    [HttpPost]
    [Consumes("multipart/form-data")]
    public async Task<IActionResult> HandleRequest()
    {
        var requestId = Guid.NewGuid().ToString("N")[..8];
        var startTime = DateTime.UtcNow;

        _logger.LogInformation("Gateway request {RequestId} started from {RemoteIP}", 
            requestId, Request.HttpContext.Connection.RemoteIpAddress);

        try
        {
            // Parse multipart/form-data to extract mx.dat file
            var mxDatData = await _multipartParser.ExtractMxDataAsync(Request.ContentType!, Request.Body, requestId);
            if (mxDatData == null || mxDatData.Length == 0)
            {
                _logger.LogWarning("No mx.dat data found in request {RequestId}", requestId);
                return BadRequest(new { error = "Missing mx.dat file" });
            }

            _logger.LogDebug("Extracted {DataSize} bytes from mx.dat in request {RequestId}", 
                mxDatData.Length, requestId);

            // Decode the request through the codec pipeline
            var (jsonString, codecInfo) = await _codecRegistry.DecodeAsync(mxDatData, requestId);
            var gameRequest = System.Text.Json.JsonSerializer.Deserialize<GameRequest>(jsonString) ?? throw new InvalidOperationException("Failed to deserialize GameRequest");
            gameRequest.RequestId = requestId;
            
            _logger.LogInformation("Decoded request {RequestId}: Protocol={Protocol}, Size={Size} bytes", 
                requestId, gameRequest.GetProtocolIdentifier(), mxDatData.Length);

            // Get or create session
            var session = await _sessionManager.GetOrCreateSessionAsync(HttpContext, requestId);

            // Capture any tokens from request headers
            await CaptureTokensAsync(Request, session);

            // Route to appropriate handler
            var responseObject = await _protocolRouter.RouteRequestAsync(gameRequest, session, requestId);

            // Create the official server response format with packet-only encoding
            var serverPacket = await CreateOfficialResponseAsync(gameRequest, responseObject, requestId);

            // Serialize the outer ServerPacket wrapper as plain JSON
            var responseJson = JsonConvert.SerializeObject(serverPacket, Formatting.None);
            var responseBytes = Encoding.UTF8.GetBytes(responseJson);

            // Set response headers for plain JSON response
            Response.ContentType = "application/json; charset=utf-8";
            Response.ContentLength = responseBytes.Length;

            // Apply session cookies and tokens
            await _sessionManager.UpdateSessionCookieAsync(HttpContext, session);

            var duration = DateTime.UtcNow - startTime;
            _logger.LogInformation("Gateway request {RequestId} completed in {Duration}ms, response size: {Size} bytes",
                requestId, duration.TotalMilliseconds, responseBytes.Length);

            return File(responseBytes, "application/json");
        }
        catch (Exception ex)
        {
            var duration = DateTime.UtcNow - startTime;
            _logger.LogError(ex, "Gateway request {RequestId} failed after {Duration}ms", requestId, duration.TotalMilliseconds);

            // Return error response as plain JSON (no encoding for errors)
            var errorObject = new { error = ex.Message };
            var errorPacketJson = JsonConvert.SerializeObject(errorObject, Formatting.None);
            var errorResponse = new BlueArchiveAPI.Models.ServerPacket("Error", errorPacketJson);
            var errorJson = JsonConvert.SerializeObject(errorResponse, Formatting.None);
            var errorBytes = Encoding.UTF8.GetBytes(errorJson);

            Response.ContentType = "application/json; charset=utf-8";
            Response.ContentLength = errorBytes.Length;

            return File(errorBytes, "application/json");
        }
    }

    /// <summary>
    /// Creates the official server response format with protocol string and encoded packet
    /// Only the packet property is compressed/encrypted, the outer wrapper remains plain JSON
    /// </summary>
    /// <param name="request">The original game request</param>
    /// <param name="responseObject">The response object from the handler</param>
    /// <param name="requestId">Request correlation ID</param>
    /// <returns>ServerPacket in official format</returns>
    private async Task<BlueArchiveAPI.Models.ServerPacket> CreateOfficialResponseAsync(GameRequest request, object responseObject, string requestId)
    {
        // Get the protocol name as string
        string protocolString;
        
        if (!string.IsNullOrEmpty(request.Protocol))
        {
            protocolString = request.Protocol;
        }
        else if (request.ProtocolCode.HasValue)
        {
            // Convert numeric protocol code to string name
            protocolString = ProtocolRouter.GetProtocolName(request.ProtocolCode.Value) ?? request.ProtocolCode.Value.ToString();
        }
        else
        {
            protocolString = "Unknown";
        }

        // Serialize the response object as the packet content
        var packetJson = JsonConvert.SerializeObject(responseObject, Formatting.None);
        
        // Apply compression/encryption only to the packet content
        var encodedPacketBytes = await _codecRegistry.EncodeAsync(packetJson, requestId);
        
        // Convert encoded bytes to base64 if compression/encryption was applied,
        // otherwise keep as plain JSON string
        string packetContent;
        if (encodedPacketBytes.Length != Encoding.UTF8.GetBytes(packetJson).Length ||
            !Encoding.UTF8.GetString(encodedPacketBytes).Equals(packetJson))
        {
            // Data was encoded, use base64
            packetContent = Convert.ToBase64String(encodedPacketBytes);
            _logger.LogDebug("Packet encoded to base64 for request {RequestId}, size: {Size} -> {EncodedSize}",
                requestId, packetJson.Length, packetContent.Length);
        }
        else
        {
            // Data was not encoded (pass-through), use as plain string
            packetContent = packetJson;
            _logger.LogDebug("Packet passed through without encoding for request {RequestId}, size: {Size}",
                requestId, packetJson.Length);
        }
        
        return new BlueArchiveAPI.Models.ServerPacket(protocolString, packetContent);
    }

    /// <summary>
    /// Health check endpoint for the gateway
    /// </summary>
    [HttpGet("health")]
    public IActionResult Health()
    {
        return Ok(new 
        { 
            status = "healthy", 
            timestamp = DateTime.UtcNow,
            version = "1.0.0",
            gateway = "BlueArchiveAPI-Gateway"
        });
    }

    /// <summary>
    /// Get registered protocol handlers for debugging
    /// </summary>
    [HttpGet("protocols")]
    public IActionResult GetProtocols()
    {
        var handlers = _protocolRouter.GetRegisteredHandlers();
        return Ok(new
        {
            handlers = handlers,
            count = handlers.Count,
            timestamp = DateTime.UtcNow
        });
    }

    /// <summary>
    /// Captures tokens from request headers and stores them in the session for reuse
    /// </summary>
    /// <param name="request">HTTP request</param>
    /// <param name="session">Game session</param>
    /// <returns>Task</returns>
    private async Task CaptureTokensAsync(HttpRequest request, GameSession session)
    {
        // Capture MxToken if present
        if (request.Headers.TryGetValue("MxToken", out var mxToken))
        {
            session.MxToken = mxToken.FirstOrDefault();
            _logger.LogDebug("Captured MxToken for session {SessionId}", session.SessionId);
        }

        // Comprehensive cookie capture for session reuse after flip
        // Capture ALL cookies except system/security sensitive ones
        var excludedCookies = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            // .NET/ASP.NET system cookies
            ".AspNetCore.Session",
            ".AspNetCore.Identity.Application",
            ".AspNetCore.Antiforgery",
            ".AspNetCore.Cookies",
            "__RequestVerificationToken",
            
            // Browser security cookies
            "__Host-",
            "__Secure-",
            
            // Analytics/tracking (optional - can be removed if needed)
            "_ga", "_gid", "_gat", "_gtag", "_fbp", "_fbc"
        };

        var capturedCount = 0;
        var skippedCount = 0;

        foreach (var cookie in request.Cookies)
        {
            // Skip excluded system/security cookies
            if (excludedCookies.Any(excluded => cookie.Key.StartsWith(excluded, StringComparison.OrdinalIgnoreCase)))
            {
                skippedCount++;
                _logger.LogTrace("Skipped system cookie {CookieName} for session {SessionId}", cookie.Key, session.SessionId);
                continue;
            }

            // Capture all other cookies for reuse
            var previousValue = session.Cookies.GetValueOrDefault(cookie.Key);
            if (previousValue != cookie.Value)
            {
                session.Cookies[cookie.Key] = cookie.Value;
                capturedCount++;
                _logger.LogDebug("Captured cookie {CookieName}={CookieValue} for session {SessionId}",
                    cookie.Key, cookie.Value, session.SessionId);
            }
        }

        if (capturedCount > 0)
        {
            _logger.LogInformation("Captured {CapturedCount} cookies ({SkippedCount} skipped) for session {SessionId}",
                capturedCount, skippedCount, session.SessionId);
        }

        await Task.CompletedTask;
    }
}