using GameGateway.Interfaces;
using GameGateway.Models;
using System.Text.Json;

namespace GameGateway.Services;

/// <summary>
/// Routes protocol requests to appropriate handlers
/// </summary>
public class ProtocolRouter
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<ProtocolRouter> _logger;
    private readonly Dictionary<string, Type> _stringProtocolHandlers;
    private readonly Dictionary<int, Type> _numericProtocolHandlers;

    public ProtocolRouter(IServiceProvider serviceProvider, ILogger<ProtocolRouter> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
        _stringProtocolHandlers = new Dictionary<string, Type>(StringComparer.OrdinalIgnoreCase);
        _numericProtocolHandlers = new Dictionary<int, Type>();
        
        RegisterHandlers();
    }

    /// <summary>
    /// Registers all protocol handlers from DI container
    /// </summary>
    private void RegisterHandlers()
    {
        var handlerServices = _serviceProvider.GetServices<IProtocolHandler>();
        
        foreach (var handler in handlerServices)
        {
            var handlerType = handler.GetType();
            
            if (!string.IsNullOrEmpty(handler.ProtocolName))
            {
                _stringProtocolHandlers[handler.ProtocolName] = handlerType;
                _logger.LogDebug("Registered string protocol handler: {ProtocolName} -> {HandlerType}", 
                    handler.ProtocolName, handlerType.Name);
            }
            
            if (handler.ProtocolCode.HasValue)
            {
                _numericProtocolHandlers[handler.ProtocolCode.Value] = handlerType;
                _logger.LogDebug("Registered numeric protocol handler: {ProtocolCode} -> {HandlerType}", 
                    handler.ProtocolCode.Value, handlerType.Name);
            }
        }
        
        _logger.LogInformation("Registered {StringHandlers} string and {NumericHandlers} numeric protocol handlers",
            _stringProtocolHandlers.Count, _numericProtocolHandlers.Count);
    }

    /// <summary>
    /// Routes a request to the appropriate protocol handler
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
    /// Routes a request to the appropriate protocol handler (internal method)
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
        IProtocolHandler? handler = null;
        string handlerName = "Unknown";

        try
        {
            // Try to resolve handler by string protocol name first
            if (!string.IsNullOrEmpty(request.Protocol))
            {
                if (_stringProtocolHandlers.TryGetValue(request.Protocol, out var stringHandlerType))
                {
                    handler = (IProtocolHandler)_serviceProvider.GetRequiredService(stringHandlerType);
                    handlerName = request.Protocol;
                }
            }
            
            // Fallback to numeric protocol code
            if (handler == null && request.ProtocolCode.HasValue)
            {
                if (_numericProtocolHandlers.TryGetValue(request.ProtocolCode.Value, out var numericHandlerType))
                {
                    handler = (IProtocolHandler)_serviceProvider.GetRequiredService(numericHandlerType);
                    handlerName = request.ProtocolCode.Value.ToString();
                }
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
            
            var response = await handler.HandleAsync(request, session, requestId, cancellationToken);
            
            var duration = DateTime.UtcNow - startTime;
            _logger.LogInformation("Handler {HandlerName} completed request {RequestId} in {Duration}ms", 
                handlerName, requestId, duration.TotalMilliseconds);

            return response;
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
        
        foreach (var kvp in _stringProtocolHandlers)
        {
            handlers[$"string:{kvp.Key}"] = kvp.Value.Name;
        }
        
        foreach (var kvp in _numericProtocolHandlers)
        {
            handlers[$"numeric:{kvp.Key}"] = kvp.Value.Name;
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
        if (!string.IsNullOrEmpty(protocol) && _stringProtocolHandlers.ContainsKey(protocol))
            return true;
            
        if (protocolCode.HasValue && _numericProtocolHandlers.ContainsKey(protocolCode.Value))
            return true;
            
        return false;
    }
}