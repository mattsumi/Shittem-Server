using System.Text.Json.Nodes;

namespace ShittimServer.Admin;

public sealed record MailAttachment(int ItemId, int Count, string? Note);
public sealed record SendMailRequest(long AccountId, string Subject, string Body, List<MailAttachment>? Attachments);
public sealed record PublishNoticeRequest(string Title, string Text, string? StartsAt, string? EndsAt, int Priority = 1);

// Small model for authoritative account data captured from official gateway responses
public sealed class AccountSnapshot
{
    public long AccountId { get; set; }
    public string? Nickname { get; set; }
    public int? Level { get; set; }
    public int? Pyroxene { get; set; }
    public int? PaidPyroxene { get; set; }
    public int? FreePyroxene { get; set; }
    public int? Credits { get; set; }
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}

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
