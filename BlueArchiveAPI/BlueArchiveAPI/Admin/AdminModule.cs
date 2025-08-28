using BlueArchiveAPI.Admin;
using BlueArchiveAPI.Gateway.Services;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace BlueArchiveAPI.Admin;

public static class AdminModule
{
    private static readonly JsonSerializerOptions JsonOpts = new(JsonSerializerDefaults.Web) { WriteIndented = true };

    public static IServiceCollection AddAdminModule(this IServiceCollection services, string dataRoot = "data")
    {
        services.AddSingleton<IAdminStore>(_ => new FileAdminStore(Path.Combine(AppContext.BaseDirectory, dataRoot, "AdminData")));
        return services;
    }

    public static IEndpointRouteBuilder MapAdminApi(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/admin")
                       .WithTags("Admin");

        // Health
        group.MapGet("/health", () => Results.Ok(new { ok = true, now = DateTimeOffset.UtcNow }));

        // Fetch account JSON
        group.MapGet("/account/{id:long}", async (long id, IAdminStore store) =>
        {
            var snap = await store.GetAsync(id) ?? new AccountSnapshot(id, new JsonObject());
            return Results.Json(snap.Data, JsonOpts);
        });

        // Patch/replace account JSON (accept any JSON and merge shallowly)
        group.MapPost("/account/{id:long}", async (long id, HttpRequest req, IAdminStore store) =>
        {
            var body = await JsonNode.ParseAsync(req.Body) as JsonObject ?? new JsonObject();
            await store.PatchAsync(id, s =>
            {
                foreach (var kv in body)
                {
                    s.Data[kv.Key] = kv.Value?.DeepClone();
                }
                s.UpdatedAt = DateTimeOffset.UtcNow;
            });

            var updated = await store.GetAsync(id);
            return Results.Json(updated?.Data ?? new JsonObject(), JsonOpts);
        });

        // Send in-game mail (simple echo for now; plug real persistence later)
        group.MapPost("/mail", async (HttpRequest req) =>
        {
            var payload = await req.ReadFromJsonAsync<MailRequest>();
            if (payload is null) return Results.BadRequest("Invalid JSON");

            var mail = new JsonObject
            {
                ["Subject"] = payload.Subject,
                ["Body"] = payload.Body,
                ["CreatedAt"] = DateTimeOffset.UtcNow.ToString("o"),
                ["Attachments"] = new JsonArray((payload.Attachments ?? new()).Select(a =>
                    new JsonObject { ["ItemId"] = a.ItemId, ["Count"] = a.Count, ["Note"] = a.Note ?? "" }).ToArray())
            };

            return Results.Json(new { ok = true, accountId = payload.AccountId, mail }, JsonOpts);
        });

        // Publish notice (simple echo for now)
        group.MapPost("/notice", async (HttpRequest req) =>
        {
            var payload = await req.ReadFromJsonAsync<NoticeRequest>();
            if (payload is null) return Results.BadRequest("Invalid JSON");

            var notice = new JsonObject
            {
                ["Title"] = payload.Title,
                ["Text"] = payload.Text,
                ["StartsAt"] = (payload.StartsAt ?? DateTimeOffset.UtcNow).ToString("o"),
                ["EndsAt"] = (payload.EndsAt ?? DateTimeOffset.UtcNow.AddDays(7)).ToString("o"),
                ["Priority"] = payload.Priority
            };

            return Results.Json(new { ok = true, notice }, JsonOpts);
        });

        // (Optional) fetch current notices (no persistence yet)
        group.MapGet("/notice", () => Results.Json(Array.Empty<NoticeRequest>(), JsonOpts));

        return group;
    }
}
