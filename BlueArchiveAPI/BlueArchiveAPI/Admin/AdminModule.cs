using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;

namespace ShittimServer.Admin;

public static class AdminModule
{
    private static readonly JsonSerializerOptions JsonOpts = new(JsonSerializerDefaults.Web) { WriteIndented = true };

    public static IServiceCollection AddAdminModule(this IServiceCollection services, string dataRoot = "data")
    {
        services.AddSingleton<IAdminStore>(_ => new FileAdminStore(Path.Combine(AppContext.BaseDirectory, dataRoot)));
        return services;
    }

    public static IEndpointRouteBuilder MapAdminApi(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/admin")
                       .WithTags("Admin");

        // Health
        group.MapGet("/health", () => Results.Ok(new { ok = true, now = DateTimeOffset.UtcNow }));

        // Fetch account JSON
        group.MapGet("/account/{id:long}", (long id, IAdminStore store) =>
        {
            try
            {
                var doc = store.GetOrCreateAccount(id);
                return Results.Json(doc.Data, JsonOpts);
            }
            catch (Exception e)
            {
                return Results.Problem(e.Message, statusCode: StatusCodes.Status404NotFound);
            }
        });

        // Patch/replace account JSON (accept any JSON and merge shallowly)
        group.MapPost("/account/{id:long}", async (long id, HttpRequest req, IAdminStore store) =>
        {
            var body = await JsonNode.ParseAsync(req.Body) as JsonObject ?? new JsonObject();

            var current = store.GetOrCreateAccount(id);
            foreach (var kv in body)
            {
                current.Data[kv.Key] = kv.Value?.DeepClone();
            }
            store.UpsertAccount(current);
            return Results.Json(current.Data, JsonOpts);
        });

        // Send in-game mail
        group.MapPost("/mail", async (HttpRequest req, IAdminStore store) =>
        {
            var payload = await req.ReadFromJsonAsync<SendMailRequest>();
            if (payload is null) return Results.BadRequest("Invalid JSON");

            var mail = new JsonObject
            {
                ["Subject"] = payload.Subject,
                ["Body"] = payload.Body,
                ["CreatedAt"] = DateTimeOffset.UtcNow.ToString("o"),
                ["Attachments"] = new JsonArray((payload.Attachments ?? new()).Select(a =>
                    new JsonObject { ["ItemId"] = a.ItemId, ["Count"] = a.Count, ["Note"] = a.Note ?? "" }).ToArray())
            };

            store.AppendMail(payload.AccountId, mail);
            return Results.Json(new { ok = true, accountId = payload.AccountId, mail }, JsonOpts);
        });

        // Publish notice
        group.MapPost("/notice", async (HttpRequest req, IAdminStore store) =>
        {
            var payload = await req.ReadFromJsonAsync<PublishNoticeRequest>();
            if (payload is null) return Results.BadRequest("Invalid JSON");

            var notice = new JsonObject
            {
                ["Title"] = payload.Title,
                ["Text"] = payload.Text,
                ["StartsAt"] = payload.StartsAt ?? DateTimeOffset.UtcNow.ToString("o"),
                ["EndsAt"] = payload.EndsAt ?? DateTimeOffset.UtcNow.AddDays(7).ToString("o"),
                ["Priority"] = payload.Priority
            };

            store.AppendNotice(notice);
            return Results.Json(new { ok = true, notice }, JsonOpts);
        });

        // (Optional) fetch current notices (handy while wiring the client)
        group.MapGet("/notice", (IAdminStore store) => Results.Json(store.GetNotices(), JsonOpts));

        return group;
    }
}
