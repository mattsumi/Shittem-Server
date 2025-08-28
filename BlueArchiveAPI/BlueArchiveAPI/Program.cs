using BlueArchiveAPI.Admin;
using BlueArchiveAPI.Catalog;
using BlueArchiveAPI.Gateway.Compression;
using BlueArchiveAPI.Gateway.Crypto;
using BlueArchiveAPI.Gateway.Interfaces;
using BlueArchiveAPI.Gateway.Services;
using BlueArchiveAPI.Handlers;
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

builder.Services.AddSingleton<IEntityCatalog>(sp =>
{
    var env = sp.GetRequiredService<IHostEnvironment>();
    var primary = Path.Combine(env.ContentRootPath, "data");
    var fallback = Path.GetFullPath(Path.Combine(env.ContentRootPath, "..", "..", "data"));
    var fromEnv = Environment.GetEnvironmentVariable("CATALOG_DATA_DIR");
    var dataDir = Directory.Exists(primary) ? primary :
                  (!string.IsNullOrEmpty(fromEnv) && Directory.Exists(fromEnv) ? fromEnv :
                  (Directory.Exists(fallback) ? fallback : primary));
    Log.Information("[CATALOG] json data dir={DataDir}", dataDir);
    return new EntityCatalog(dataDir, "en");
});

// Register crypto adapters
builder.Services.AddSingleton<ICryptoAdapter, Aes256GcmAdapter>();
builder.Services.AddSingleton<ICryptoAdapter, ChaCha20Poly1305Adapter>();

// Register compression adapters
builder.Services.AddSingleton<ICompressionAdapter, DeflateAdapter>();

// Register Admin services
builder.Services.AddAdminModule();
builder.Services.AddControllers();
builder.Services.AddSingleton<IAdminStore, InMemoryAdminStore>();

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
