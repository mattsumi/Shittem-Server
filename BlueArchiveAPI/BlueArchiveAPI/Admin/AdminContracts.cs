using System.Text.Json.Nodes;

namespace ShittimServer.Admin;

public sealed record MailAttachment(int ItemId, int Count, string? Note);
public sealed record SendMailRequest(long AccountId, string Subject, string Body, List<MailAttachment>? Attachments);
public sealed record PublishNoticeRequest(string Title, string Text, string? StartsAt, string? EndsAt, int Priority = 1);

// We keep Account as a flexible JSON blob to let you patch arbitrary fields (Level, Pyroxene, credits, roster, etc.)
public sealed class AccountDocument
{
    public long AccountId { get; set; }
    public JsonObject Data { get; set; } = new();

    public static AccountDocument WithDefaults(long id)
    {
        var obj = new JsonObject
        {
            ["AccountId"] = id,
            ["Nickname"] = "Commander",
            ["CallName"] = "Commander",
            ["Level"] = 1,
            ["Pyroxene"] = 0,
            ["Credits"] = 0,
            ["Units"] = new JsonArray(),   // array of { UnitId, Level, Rarity, ... }
            ["Mail"] = new JsonArray(),    // array of { Subject, Body, Attachments[], CreatedAt }
        };
        return new AccountDocument { AccountId = id, Data = obj };
    }
}
