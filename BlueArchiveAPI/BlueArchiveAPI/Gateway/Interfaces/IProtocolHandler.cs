using BlueArchiveAPI.Gateway.Models;

namespace BlueArchiveAPI.Gateway.Interfaces;

/// <summary>
/// Interface for protocol-specific request handlers
/// </summary>
public interface IProtocolHandler
{
    /// <summary>
    /// Gets the protocol name handled by this handler
    /// </summary>
    string ProtocolName { get; }
    
    /// <summary>
    /// Gets the numeric protocol code handled by this handler
    /// </summary>
    int? ProtocolCode { get; }
    
    /// <summary>
    /// Handles the incoming request and produces a response payload
    /// </summary>
    /// <param name="request">The decoded request</param>
    /// <param name="session">The session context</param>
    /// <param name="requestId">The correlation ID for this request</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>The response payload to be serialized</returns>
    Task<object> HandleAsync(
        GameRequest request, 
        GameSession session, 
        string requestId,
        CancellationToken cancellationToken = default);
}