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

            // Create the official server response format
            var serverPacket = CreateOfficialResponse(gameRequest, responseObject);

            // Serialize the response
            var responseJson = JsonConvert.SerializeObject(serverPacket, Formatting.None);
            var responseBytes = Encoding.UTF8.GetBytes(responseJson);

            // Encode the response through the codec pipeline
            var encodedResponse = await _codecRegistry.EncodeAsync(responseJson, requestId);

            // Set response headers
            Response.ContentType = "application/octet-stream";
            Response.ContentLength = encodedResponse.Length;

            // Apply session cookies and tokens
            await _sessionManager.UpdateSessionCookieAsync(HttpContext, session);

            var duration = DateTime.UtcNow - startTime;
            _logger.LogInformation("Gateway request {RequestId} completed in {Duration}ms, response size: {Size} bytes", 
                requestId, duration.TotalMilliseconds, encodedResponse.Length);

            return File(encodedResponse, "application/octet-stream");
        }
        catch (Exception ex)
        {
            var duration = DateTime.UtcNow - startTime;
            _logger.LogError(ex, "Gateway request {RequestId} failed after {Duration}ms", requestId, duration.TotalMilliseconds);

            // Return error response
            var errorResponse = new ServerPacket("Error", JsonConvert.SerializeObject(new { error = ex.Message }));
            var errorJson = JsonConvert.SerializeObject(errorResponse, Formatting.None);
            var errorBytes = Encoding.UTF8.GetBytes(errorJson);

            Response.ContentType = "application/octet-stream";
            Response.ContentLength = errorBytes.Length;

            return File(errorBytes, "application/octet-stream");
        }
    }

    /// <summary>
    /// Creates the official server response format with protocol string and JSON-encoded packet
    /// </summary>
    /// <param name="request">The original game request</param>
    /// <param name="responseObject">The response object from the handler</param>
    /// <returns>ServerPacket in official format</returns>
    private ServerPacket CreateOfficialResponse(GameRequest request, object responseObject)
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
        
        return new ServerPacket(protocolString, packetJson);
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
    /// Captures tokens from request headers and stores them in the session
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

        // Capture any session-related cookies
        foreach (var cookie in request.Cookies)
        {
            if (cookie.Key.StartsWith("session", StringComparison.OrdinalIgnoreCase) ||
                cookie.Key.Equals("uuid", StringComparison.OrdinalIgnoreCase) ||
                cookie.Key.StartsWith("AWSALB", StringComparison.OrdinalIgnoreCase))
            {
                session.Cookies[cookie.Key] = cookie.Value;
                _logger.LogDebug("Captured cookie {CookieName} for session {SessionId}", cookie.Key, session.SessionId);
            }
        }

        await Task.CompletedTask;
    }
}