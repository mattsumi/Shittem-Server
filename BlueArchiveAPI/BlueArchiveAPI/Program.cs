using BlueArchiveAPI;
using BlueArchiveAPI.Controllers;
using BlueArchiveAPI.Handlers;
using BlueArchiveAPI.Models;
using BlueArchiveAPI.NetworkModels;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Security.Cryptography;
using System.Text;

HandlerManager.Initialize();

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.

builder.Services.AddResponseCompression(options =>
{
    options.EnableForHttps = true;
});


builder.Services.AddControllers();

var app = builder.Build();

// Configure the HTTP request pipeline.

app.UseResponseCompression();

// Add health endpoint for Python server to check if C# API is running
app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "BlueArchiveAPI" }));

app.MapControllers();

// app.UseMiddleware<BodyMiddleware>();

app.Run();
