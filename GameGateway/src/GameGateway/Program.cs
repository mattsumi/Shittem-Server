using GameGateway.Compression;
using GameGateway.Crypto;
using GameGateway.Handlers;
using GameGateway.Interfaces;
using GameGateway.Services;
using Microsoft.AspNetCore.ResponseCompression;
using Serilog;
using Serilog.Events;
using System.IO.Compression;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);

// Configure Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .MinimumLevel.Override("Microsoft.AspNetCore", LogEventLevel.Warning)
    .MinimumLevel.Override("System.Net.Http.HttpClient", LogEventLevel.Warning)
    .Enrich.FromLogContext()
    .WriteTo.Console(outputTemplate: 
        "[{Timestamp:yyyy-MM-dd HH:mm:ss.fff zzz}] [{Level:u3}] [{SourceContext}] {Message:lj} {NewLine}{Exception}")
    .WriteTo.File("logs/gamegateway-.log", 
        rollingInterval: RollingInterval.Day,
        retainedFileCountLimit: 30,
        outputTemplate: 
            "[{Timestamp:yyyy-MM-dd HH:mm:ss.fff zzz}] [{Level:u3}] [{SourceContext}] {Message:lj} {NewLine}{Exception}")
    .CreateLogger();

builder.Host.UseSerilog();

// Add services to the container
builder.Services.AddSingleton<IConfiguration>(builder.Configuration);

// Add memory cache for session management
builder.Services.AddMemoryCache();

// Register compression adapters
builder.Services.AddSingleton<ICompressionAdapter, DeflateAdapter>();

// Register crypto adapters
builder.Services.AddSingleton<ICryptoAdapter, Aes256GcmAdapter>();
builder.Services.AddSingleton<ICryptoAdapter, ChaCha20Poly1305Adapter>();

// Register core services
builder.Services.AddSingleton<CodecRegistry>();
builder.Services.AddSingleton<SessionManager>();
builder.Services.AddSingleton<ProtocolRouter>();
builder.Services.AddSingleton<MultipartParser>();

// Register protocol handlers (both as concrete types and IProtocolHandler)
builder.Services.AddSingleton<QueueGetTicketHandler>();
builder.Services.AddSingleton<IProtocolHandler>(provider => provider.GetRequiredService<QueueGetTicketHandler>());
builder.Services.AddSingleton<AccountCheckHandler>();
builder.Services.AddSingleton<IProtocolHandler>(provider => provider.GetRequiredService<AccountCheckHandler>());
builder.Services.AddSingleton<AccountAuthHandler>();
builder.Services.AddSingleton<IProtocolHandler>(provider => provider.GetRequiredService<AccountAuthHandler>());

// Add response compression
builder.Services.AddResponseCompression(options =>
{
    options.EnableForHttps = true;
    options.Providers.Add<GzipCompressionProvider>();
    options.MimeTypes = ResponseCompressionDefaults.MimeTypes.Concat(new[]
    {
        "application/json",
        "text/json"
    });
});

builder.Services.Configure<GzipCompressionProviderOptions>(options =>
{
    options.Level = CompressionLevel.Fastest;
});

// Configure Kestrel for HTTP/2 support
builder.WebHost.ConfigureKestrel(options =>
{
    options.ListenAnyIP(7000, listenOptions =>
    {
        listenOptions.Protocols = Microsoft.AspNetCore.Server.Kestrel.Core.HttpProtocols.Http1AndHttp2;
    });
});

// Add CORS if needed
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.AllowAnyOrigin()
              .AllowAnyMethod()
              .AllowAnyHeader();
    });
});

var app = builder.Build();

// Use response compression
app.UseResponseCompression();

// Use CORS
app.UseCors();

// Add request correlation ID middleware
app.Use(async (context, next) =>
{
    var requestId = context.Request.Headers["X-Request-ID"].FirstOrDefault() 
                   ?? Guid.NewGuid().ToString("N")[..16];
    
    using (Serilog.Context.LogContext.PushProperty("RequestId", requestId))
    {
        context.Response.Headers["X-Request-ID"] = requestId;
        await next();
    }
});

// Add request logging middleware
app.UseSerilogRequestLogging(options =>
{
    options.MessageTemplate = "HTTP {RequestMethod} {RequestPath} responded {StatusCode} in {Elapsed:0.0000} ms";
    options.EnrichDiagnosticContext = (diagnosticContext, httpContext) =>
    {
        diagnosticContext.Set("RequestId", httpContext.Response.Headers["X-Request-ID"].FirstOrDefault());
        diagnosticContext.Set("ClientIP", httpContext.Connection.RemoteIpAddress?.ToString());
        diagnosticContext.Set("UserAgent", httpContext.Request.Headers["User-Agent"].FirstOrDefault());
        
        if (httpContext.Request.ContentLength.HasValue)
        {
            diagnosticContext.Set("ContentLength", httpContext.Request.ContentLength.Value);
        }
    };
});

// Health check endpoint
app.MapGet("/health", () => Results.Ok(new { 
    Status = "Healthy", 
    Timestamp = DateTime.UtcNow,
    Version = "1.0.0"
}));

// Main gateway endpoint
app.MapPost("/api/gateway", async (
    HttpContext context,
    CodecRegistry codecRegistry,
    SessionManager sessionManager,
    ProtocolRouter protocolRouter,
    MultipartParser multipartParser,
    ILogger<Program> logger) =>
{
    var requestId = context.Response.Headers["X-Request-ID"].FirstOrDefault() ?? "unknown";
    
    try
    {
        logger.LogInformation("Processing gateway request {RequestId} from {ClientIP}", 
            requestId, context.Connection.RemoteIpAddress);

        // Validate content type
        var contentType = context.Request.ContentType;
        if (string.IsNullOrEmpty(contentType) || !contentType.StartsWith("multipart/form-data", StringComparison.OrdinalIgnoreCase))
        {
            logger.LogWarning("Invalid content type for request {RequestId}: {ContentType}", requestId, contentType);
            return Results.BadRequest(new { Error = "Content-Type must be multipart/form-data" });
        }

        // Parse multipart data to extract mx.dat
        byte[] mxDatContent;
        try
        {
            var formData = await multipartParser.ParseAsync(context.Request, context.RequestAborted);
            if (!formData.TryGetValue("mx.dat", out var mxDatBytes) || mxDatBytes.Length == 0)
            {
                logger.LogWarning("No mx.dat file found in request {RequestId}", requestId);
                return Results.BadRequest(new { Error = "mx.dat file is required" });
            }
            mxDatContent = mxDatBytes;
            logger.LogDebug("Extracted mx.dat file for request {RequestId}: {Size} bytes", requestId, mxDatContent.Length);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to parse multipart data for request {RequestId}", requestId);
            return Results.BadRequest(new { Error = "Invalid multipart data" });
        }

        // Decode mx.dat content through codec pipeline
        string decodedJson;
        try
        {
            decodedJson = await codecRegistry.DecodeAsync(mxDatContent, context.RequestAborted);
            logger.LogDebug("Decoded mx.dat for request {RequestId}: {Length} characters", requestId, decodedJson.Length);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to decode mx.dat content for request {RequestId}", requestId);
            return Results.BadRequest(new { Error = "Failed to decode mx.dat content" });
        }

        // Parse decoded JSON into GameRequest
        GameGateway.Models.GameRequest gameRequest;
        try
        {
            gameRequest = JsonSerializer.Deserialize<GameGateway.Models.GameRequest>(decodedJson, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            }) ?? throw new InvalidOperationException("Deserialized request is null");
            
            logger.LogInformation("Parsed request {RequestId}: Protocol={Protocol}/{ProtocolCode}", 
                requestId, gameRequest.Protocol, gameRequest.ProtocolCode);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to parse GameRequest for request {RequestId}", requestId);
            return Results.BadRequest(new { Error = "Invalid request format" });
        }

        // Get or create session
        var session = await sessionManager.GetOrCreateSessionAsync(context, context.RequestAborted);
        logger.LogDebug("Using session {SessionId} for request {RequestId}", session.SessionId, requestId);

        // Route request to appropriate handler
        object responsePayload;
        try
        {
            responsePayload = await protocolRouter.RouteAsync(gameRequest, session, requestId, context.RequestAborted);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to route request {RequestId} for protocol {Protocol}", requestId, gameRequest.Protocol);
            return Results.Problem("Internal server error", statusCode: 500);
        }

        // Create response wrapper
        var gameResponse = new GameGateway.Models.GameResponse
        {
            Protocol = gameRequest.ProtocolCode ?? 0,
            ResultState = 1,
            ServerTimeTicks = DateTime.UtcNow.Ticks,
            Payload = responsePayload
        };

        // Serialize response to JSON
        string responseJson;
        try
        {
            responseJson = JsonSerializer.Serialize(gameResponse, new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            });
            logger.LogDebug("Serialized response for request {RequestId}: {Length} characters", requestId, responseJson.Length);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to serialize response for request {RequestId}", requestId);
            return Results.Problem("Failed to serialize response", statusCode: 500);
        }

        // Encode response through codec pipeline
        byte[] encodedResponse;
        try
        {
            encodedResponse = await codecRegistry.EncodeAsync(responseJson, context.RequestAborted);
            logger.LogDebug("Encoded response for request {RequestId}: {Size} bytes", requestId, encodedResponse.Length);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to encode response for request {RequestId}", requestId);
            return Results.Problem("Failed to encode response", statusCode: 500);
        }

        // Update session in response
        await sessionManager.UpdateSessionCookieAsync(context, session);

        // Return encoded response
        logger.LogInformation("Successfully processed request {RequestId}: {ResponseSize} bytes", requestId, encodedResponse.Length);
        
        return Results.File(encodedResponse, "application/octet-stream");
    }
    catch (Exception ex)
    {
        logger.LogError(ex, "Unhandled exception processing request {RequestId}", requestId);
        return Results.Problem("Internal server error", statusCode: 500);
    }
});

// Configure the HTTP request pipeline
if (app.Environment.IsDevelopment())
{
    app.UseDeveloperExceptionPage();
}

try
{
    Log.Information("Starting GameGateway service on http://0.0.0.0:7000");
    await app.RunAsync();
}
catch (Exception ex)
{
    Log.Fatal(ex, "GameGateway service terminated unexpectedly");
    throw;
}
finally
{
    Log.CloseAndFlush();
}