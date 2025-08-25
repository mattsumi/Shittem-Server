using BlueArchiveAPI.Gateway.Models;
using Microsoft.Extensions.Caching.Memory;
using System.Text.Json;

namespace BlueArchiveAPI.Gateway.Services;

/// <summary>
/// Manages game sessions with UUID cookies and MxToken handling
/// </summary>
public class SessionManager
{
    private readonly IMemoryCache _cache;
    private readonly IConfiguration _configuration;
    private readonly ILogger<SessionManager> _logger;
    private readonly TimeSpan _sessionExpiry;
    private readonly string _cookieName;
    private readonly string _cookiePath;

    public SessionManager(
        IMemoryCache cache,
        IConfiguration configuration, 
        ILogger<SessionManager> logger)
    {
        _cache = cache;
        _configuration = configuration;
        _logger = logger;
        
        var sessionConfig = configuration.GetSection("GameGateway:Session");
        _cookieName = sessionConfig.GetValue<string>("CookieName") ?? "uuid";
        _cookiePath = sessionConfig.GetValue<string>("CookiePath") ?? "/";
        _sessionExpiry = TimeSpan.FromHours(24); // Default 24 hours
        
        _logger.LogInformation("SessionManager initialized with cookie name: {CookieName}, path: {CookiePath}",
            _cookieName, _cookiePath);
    }

    /// <summary>
    /// Gets or creates a session for the request
    /// </summary>
    /// <param name="httpContext">HTTP context</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>The game session</returns>
    public async Task<GameSession> GetOrCreateSessionAsync(HttpContext httpContext, CancellationToken cancellationToken = default)
    {
        var requestId = httpContext.Response.Headers["X-Request-ID"].FirstOrDefault() ?? "unknown";
        return await GetOrCreateSessionAsync(httpContext, requestId);
    }

    /// <summary>
    /// Gets or creates a session for the request (internal method)
    /// </summary>
    /// <param name="httpContext">HTTP context</param>
    /// <param name="requestId">Request correlation ID</param>
    /// <returns>The game session</returns>
    public async Task<GameSession> GetOrCreateSessionAsync(HttpContext httpContext, string requestId)
    {
        var sessionId = GetSessionIdFromCookie(httpContext);
        GameSession? session = null;

        if (!string.IsNullOrEmpty(sessionId))
        {
            // Try to retrieve existing session
            var cacheKey = GetCacheKey(sessionId);
            if (_cache.TryGetValue(cacheKey, out var cachedSessionData))
            {
                try
                {
                    var sessionJson = (string)cachedSessionData;
                    session = JsonSerializer.Deserialize<GameSession>(sessionJson);
                    
                    if (session != null)
                    {
                        session.Touch();
                        _logger.LogDebug("Retrieved existing session {SessionId} for request {RequestId}", 
                            sessionId, requestId);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(ex, "Failed to deserialize cached session {SessionId} for request {RequestId}", 
                        sessionId, requestId);
                    session = null;
                }
            }
        }

        // Create new session if none found or failed to load
        if (session == null)
        {
            sessionId = GenerateNewSessionId();
            session = new GameSession
            {
                SessionId = sessionId,
                CreatedAt = DateTime.UtcNow,
                LastAccessedAt = DateTime.UtcNow
            };

            _logger.LogInformation("Created new session {SessionId} for request {RequestId}", 
                sessionId, requestId);

            // Set the UUID cookie
            SetSessionCookie(httpContext, sessionId);
        }

        // Update session in cache
        await StoreSessionAsync(session);

        return session;
    }

    /// <summary>
    /// Stores a session in the cache
    /// </summary>
    /// <param name="session">Session to store</param>
    public async Task StoreSessionAsync(GameSession session)
    {
        try
        {
            var cacheKey = GetCacheKey(session.SessionId);
            var sessionJson = JsonSerializer.Serialize(session);
            
            var cacheOptions = new MemoryCacheEntryOptions
            {
                SlidingExpiration = _sessionExpiry,
                Priority = CacheItemPriority.Normal
            };

            _cache.Set(cacheKey, sessionJson, cacheOptions);
            
            _logger.LogDebug("Stored session {SessionId} in cache", session.SessionId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to store session {SessionId} in cache", session.SessionId);
            throw;
        }
    }

    /// <summary>
    /// Removes a session from the cache
    /// </summary>
    /// <param name="sessionId">Session ID to remove</param>
    public void RemoveSession(string sessionId)
    {
        var cacheKey = GetCacheKey(sessionId);
        _cache.Remove(cacheKey);
        _logger.LogDebug("Removed session {SessionId} from cache", sessionId);
    }

    /// <summary>
    /// Gets the session ID from the request cookie
    /// </summary>
    private string? GetSessionIdFromCookie(HttpContext httpContext)
    {
        return httpContext.Request.Cookies[_cookieName];
    }

    /// <summary>
    /// Sets the session cookie in the response
    /// </summary>
    private void SetSessionCookie(HttpContext httpContext, string sessionId)
    {
        var cookieOptions = new CookieOptions
        {
            Path = _cookiePath,
            HttpOnly = false, // Allow JavaScript access for debugging
            SameSite = httpContext.Request.IsHttps ? SameSiteMode.None : SameSiteMode.Lax,
            Secure = httpContext.Request.IsHttps,
            Expires = DateTimeOffset.UtcNow.Add(_sessionExpiry)
        };

        httpContext.Response.Cookies.Append(_cookieName, sessionId, cookieOptions);
        
        _logger.LogDebug("Set session cookie {CookieName}={SessionId} with options: Path={Path}, Secure={Secure}, SameSite={SameSite}",
            _cookieName, sessionId, cookieOptions.Path, cookieOptions.Secure, cookieOptions.SameSite);
    }

    /// <summary>
    /// Generates a new UUID v4 session ID
    /// </summary>
    private static string GenerateNewSessionId()
    {
        return Guid.NewGuid().ToString();
    }

    /// <summary>
    /// Gets the cache key for a session ID
    /// </summary>
    private static string GetCacheKey(string sessionId)
    {
        return $"session:{sessionId}";
    }

    /// <summary>
    /// Sets load balancer cookies as specified in requirements
    /// </summary>
    public void SetLoadBalancerCookies(HttpContext httpContext)
    {
        var lbConfig = _configuration.GetSection("GameGateway:LoadBalancer:Cookies");
        var lbValue = lbConfig.GetValue<string>("LB") ?? "node1";
        var lbCorsValue = lbConfig.GetValue<string>("LBCORS") ?? "cors1";
        
        var expiry = DateTimeOffset.UtcNow.AddDays(7); // Week in the future
        
        var cookieOptions = new CookieOptions
        {
            Path = "/",
            HttpOnly = false,
            SameSite = httpContext.Request.IsHttps ? SameSiteMode.None : SameSiteMode.Lax,
            Secure = httpContext.Request.IsHttps,
            Expires = expiry
        };

        httpContext.Response.Cookies.Append("AWSALB", lbValue, cookieOptions);
        httpContext.Response.Cookies.Append("AWSALBCORS", lbCorsValue, cookieOptions);
        
        _logger.LogDebug("Set load balancer cookies: AWSALB={LB}, AWSALBCORS={LBCORS}", lbValue, lbCorsValue);
    }

    /// <summary>
    /// Gets session statistics for monitoring
    /// </summary>
    /// <returns>Dictionary of session statistics</returns>
    public Dictionary<string, object> GetSessionStats()
    {
        // Note: IMemoryCache doesn't expose count directly, so this is a placeholder
        // In production, you might want to use a more sophisticated cache or tracking
        return new Dictionary<string, object>
        {
            { "cache_type", "memory" },
            { "session_expiry_hours", _sessionExpiry.TotalHours },
            { "cookie_name", _cookieName },
            { "cookie_path", _cookiePath }
        };
    }

    /// <summary>
    /// Updates the session cookie in the response after processing
    /// </summary>
    /// <param name="httpContext">HTTP context</param>
    /// <param name="session">Session to update</param>
    /// <returns>Task</returns>
    public async Task UpdateSessionCookieAsync(HttpContext httpContext, GameSession session)
    {
        // Store updated session
        await StoreSessionAsync(session);
        
        // Update the session cookie with any new values
        SetSessionCookie(httpContext, session.SessionId);
        
        // Apply all captured session cookies to the response
        ApplyCapturedCookies(httpContext, session);
        
        // Set load balancer cookies from configuration as fallback
        SetLoadBalancerCookies(httpContext);
    }

    /// <summary>
    /// Applies all captured cookies from the session to the response
    /// This ensures cookies captured from official server requests are reused on subsequent responses
    /// </summary>
    /// <param name="httpContext">HTTP context</param>
    /// <param name="session">Game session containing captured cookies</param>
    private void ApplyCapturedCookies(HttpContext httpContext, GameSession session)
    {
        if (session.Cookies == null || session.Cookies.Count == 0)
        {
            _logger.LogDebug("No captured cookies to apply for session {SessionId}", session.SessionId);
            return;
        }

        var cookieOptions = new CookieOptions
        {
            Path = "/",
            HttpOnly = false, // Allow JavaScript access for compatibility
            SameSite = httpContext.Request.IsHttps ? SameSiteMode.None : SameSiteMode.Lax,
            Secure = httpContext.Request.IsHttps,
            Expires = DateTimeOffset.UtcNow.AddDays(7) // Default 7-day expiry
        };

        foreach (var capturedCookie in session.Cookies)
        {
            // Apply the captured cookie to the response
            httpContext.Response.Cookies.Append(capturedCookie.Key, capturedCookie.Value, cookieOptions);
            
            _logger.LogDebug("Applied captured cookie {CookieName}={CookieValue} to response for session {SessionId}",
                capturedCookie.Key, capturedCookie.Value, session.SessionId);
        }

        _logger.LogInformation("Applied {CookieCount} captured cookies to response for session {SessionId}",
            session.Cookies.Count, session.SessionId);
    }
}