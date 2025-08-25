using GameGateway.Interfaces;
using GameGateway.Models;
using System.Text.Json.Serialization;

namespace GameGateway.Handlers;

/// <summary>
/// Handler for Queue_GetTicket protocol
/// </summary>
public class QueueGetTicketHandler : IProtocolHandler
{
    private readonly IConfiguration _configuration;
    private readonly ILogger<QueueGetTicketHandler> _logger;
    private readonly Random _random;
    private readonly bool _deterministicMode;

    public string ProtocolName => "Queue_GetTicket";
    public int? ProtocolCode => 10001; // Example numeric code

    public QueueGetTicketHandler(IConfiguration configuration, ILogger<QueueGetTicketHandler> logger)
    {
        _configuration = configuration;
        _logger = logger;
        
        var testingConfig = configuration.GetSection("GameGateway:Testing");
        _deterministicMode = testingConfig.GetValue<bool>("DeterministicMode");
        var fixedSeed = testingConfig.GetValue<int>("FixedSeed", 12345);
        
        _random = _deterministicMode ? new Random(fixedSeed) : new Random();
        
        _logger.LogDebug("QueueGetTicketHandler initialized with deterministic mode: {DeterministicMode}", _deterministicMode);
    }

    public async Task<object> HandleAsync(
        GameRequest request, 
        GameSession session, 
        string requestId, 
        CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Processing Queue_GetTicket request {RequestId} for session {SessionId}", 
            requestId, session.SessionId);

        try
        {
            // Generate or retrieve deterministic values for testing
            var enterTicket = _deterministicMode ? "TICKET_12345" : GenerateEnterTicket();
            var ticketSequence = _deterministicMode ? 1000 : _random.Next(1000, 9999);
            var allowedSequence = _deterministicMode ? 100 : _random.Next(50, 200);
            var requiredSecondsPerUser = _deterministicMode ? 30 : _random.Next(10, 60);
            var serverSeed = _deterministicMode ? 987654321 : _random.Next(100000000, 999999999);

            var response = new QueueGetTicketResponse
            {
                Protocol = ProtocolCode ?? 10001,
                EnterTicket = enterTicket,
                TicketSequence = ticketSequence,
                AllowedSequence = allowedSequence,
                RequiredSecondsPerUser = requiredSecondsPerUser,
                ServerSeed = serverSeed,
                ServerTimeTicks = DateTime.UtcNow.Ticks
            };

            _logger.LogDebug("Generated Queue_GetTicket response for request {RequestId}: Ticket={EnterTicket}, Sequence={TicketSequence}", 
                requestId, enterTicket, ticketSequence);

            return response;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to process Queue_GetTicket request {RequestId}", requestId);
            throw;
        }
    }

    /// <summary>
    /// Generates a random enter ticket
    /// </summary>
    private string GenerateEnterTicket()
    {
        var ticketBytes = new byte[16];
        _random.NextBytes(ticketBytes);
        return "TICKET_" + Convert.ToBase64String(ticketBytes).Replace("+", "").Replace("/", "").Replace("=", "")[..12];
    }
}

/// <summary>
/// Response payload for Queue_GetTicket
/// </summary>
public class QueueGetTicketResponse : BaseResponsePayload
{
    /// <summary>
    /// Enter ticket identifier
    /// </summary>
    [JsonPropertyName("EnterTicket")]
    public string EnterTicket { get; set; } = string.Empty;

    /// <summary>
    /// Ticket sequence number
    /// </summary>
    [JsonPropertyName("TicketSequence")]
    public int TicketSequence { get; set; }

    /// <summary>
    /// Allowed sequence number
    /// </summary>
    [JsonPropertyName("AllowedSequence")]
    public int AllowedSequence { get; set; }

    /// <summary>
    /// Required seconds per user
    /// </summary>
    [JsonPropertyName("RequiredSecondsPerUser")]
    public int RequiredSecondsPerUser { get; set; }

    /// <summary>
    /// Server seed for randomization
    /// </summary>
    [JsonPropertyName("ServerSeed")]
    public int ServerSeed { get; set; }
}