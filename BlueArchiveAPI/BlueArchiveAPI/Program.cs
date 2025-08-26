using BlueArchiveAPI;
using BlueArchiveAPI.Controllers;
using BlueArchiveAPI.Handlers;
using BlueArchiveAPI.Models;
using BlueArchiveAPI.NetworkModels;
using BlueArchiveAPI.Gateway.Services;
using BlueArchiveAPI.Gateway.Crypto;
using BlueArchiveAPI.Gateway.Compression;
using BlueArchiveAPI.Gateway.Interfaces;
using ShittimServer.Admin;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Security.Cryptography;
using System.Text;
using Serilog;

// Configure Serilog
Log.Logger = new LoggerConfiguration()
    .WriteTo.Console()
    .WriteTo.File("logs/bluearchive-gateway-.txt", rollingInterval: RollingInterval.Day)
    .CreateLogger();

HandlerManager.Initialize();

var builder = WebApplication.CreateBuilder(args);

// Add Serilog
builder.Host.UseSerilog();

// Add CORS for local admin GUI access
builder.Services.AddCors(options =>
{
    options.AddPolicy("AdminPolicy", policy =>
    {
        policy.WithOrigins("http://127.0.0.1", "http://localhost")
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials();
    });
});

// Add services to the container
builder.Services.AddResponseCompression(options =>
{
    options.EnableForHttps = true;
});

// Add memory caching for sessions
builder.Services.AddMemoryCache();

// Register Gateway services
builder.Services.AddSingleton<MultipartParser>();
builder.Services.AddSingleton<SessionManager>();
builder.Services.AddSingleton<CodecRegistry>();
builder.Services.AddSingleton<ProtocolRouter>();

// Register crypto adapters
builder.Services.AddSingleton<ICryptoAdapter, Aes256GcmAdapter>();
builder.Services.AddSingleton<ICryptoAdapter, ChaCha20Poly1305Adapter>();

// Register compression adapters
builder.Services.AddSingleton<ICompressionAdapter, DeflateAdapter>();

// Register Admin services
builder.Services.AddAdminModule();

builder.Services.AddControllers();

var app = builder.Build();

// Configure the HTTP request pipeline
app.UseResponseCompression();

// Enable CORS for admin endpoints
app.UseCors("AdminPolicy");

app.MapControllers();

// Map admin API endpoints
app.MapAdminApi();

// app.UseMiddleware<BodyMiddleware>();

try
{
    var urls = builder.Configuration.GetValue<string>("urls") ??
               Environment.GetEnvironmentVariable("ASPNETCORE_URLS") ??
               "http://0.0.0.0:7000";
    
    Log.Information("Starting BlueArchiveAPI Gateway server");
    Log.Information("Admin API enabled at {BaseUrl}/admin", urls.Split(';')[0]);
    app.Run();
}
catch (Exception ex)
{
    Log.Fatal(ex, "Application terminated unexpectedly");
}
finally
{
    Log.CloseAndFlush();
}
