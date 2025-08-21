using BlueArchiveAPI;
using BlueArchiveAPI.Controllers;
using BlueArchiveAPI.Handlers;
using BlueArchiveAPI.Models;
using BlueArchiveAPI.NetworkModels;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using Microsoft.AspNetCore.Server.Kestrel.Https;

HandlerManager.Initialize();

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.

builder.Services.AddResponseCompression(options =>
{
    options.EnableForHttps = true;
});

builder.Services.AddControllers();

// Configure HTTPS with self-signed certificate
var certPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "..", "certs", "selfsigned_cert.pem");
var keyPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "..", "certs", "selfsigned_key.pem");

if (File.Exists(certPath) && File.Exists(keyPath))
{
    // Convert PEM to X509Certificate2
    var cert = CreateCertificateFromPem(certPath, keyPath);
    if (cert != null)
    {
        builder.WebHost.ConfigureKestrel(options =>
        {
            // HTTP on port 5000
            options.ListenAnyIP(5000);
            // HTTPS on port 5100 with our certificate
            options.ListenAnyIP(5100, listenOptions =>
            {
                listenOptions.UseHttps(cert);
            });
        });
        Console.WriteLine("✓ Using self-signed certificate for HTTPS on port 5100");
    }
    else
    {
        Console.WriteLine("✗ Failed to load certificate, using default configuration");
    }
}
else
{
    Console.WriteLine($"✗ Certificate files not found at {certPath} or {keyPath}");
    Console.WriteLine("✗ Using default HTTP configuration");
}

var app = builder.Build();

// Configure the HTTP request pipeline.

app.UseResponseCompression();

// Add health endpoint for Python server to check if C# API is running
app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "BlueArchiveAPI" }));

app.MapControllers();

// app.UseMiddleware<BodyMiddleware>();

app.Run();

static X509Certificate2? CreateCertificateFromPem(string certPath, string keyPath)
{
    try
    {
        var certPem = File.ReadAllText(certPath);
        var keyPem = File.ReadAllText(keyPath);
        
        // Create certificate from PEM strings
        var cert = X509Certificate2.CreateFromPem(certPem, keyPem);
        
        // Export and re-import to ensure private key is properly associated
        var pfxBytes = cert.Export(X509ContentType.Pkcs12);
        return new X509Certificate2(pfxBytes);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"✗ Error loading certificate: {ex.Message}");
        return null;
    }
}
