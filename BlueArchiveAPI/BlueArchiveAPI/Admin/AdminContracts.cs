// namespace BlueArchiveAPI.Admin;dminContracts.cs
using System.Text.Json.Serialization;

namespace BlueArchiveAPI.Admin
{
    // Generic wrapper so the Admin GUI can show messages
    public sealed class ApiResult<T>
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; } = true;
        [JsonPropertyName("message")] public string? Message { get; set; }
        [JsonPropertyName("data")] public T? Data { get; set; }

        public static ApiResult<T> Success(T data, string? msg = null)
            => new() { Ok = true, Message = msg, Data = data };

        public static ApiResult<T> Fail(string msg)
            => new() { Ok = false, Message = msg, Data = default };
    }

    // --- Account models ------------------------------------------------------

    public sealed class AccountSummary
    {
        [JsonPropertyName("accountId")] public long AccountId { get; set; }
        [JsonPropertyName("nickname")] public string Nickname { get; set; } = "Sensei";
        [JsonPropertyName("level")] public int Level { get; set; } = 1;
        [JsonPropertyName("pyroxene")] public int Pyroxene { get; set; } = 0;
        [JsonPropertyName("credits")] public int Credits { get; set; } = 0;

        // Minimal inventory/student collections so the GUI can grow later
        [JsonPropertyName("inventory")] public Dictionary<int, int> Inventory { get; set; } = new();
        [JsonPropertyName("students")] public List<long> Students { get; set; } = new();
    }

    public sealed class AccountPatch
    {
        [JsonPropertyName("nickname")] public string? Nickname { get; set; }
        [JsonPropertyName("level")] public int? Level { get; set; }
        [JsonPropertyName("pyroxene")] public int? Pyroxene { get; set; }
        [JsonPropertyName("credits")] public int? Credits { get; set; }
        [JsonPropertyName("inventory")] public Dictionary<int, int>? Inventory { get; set; }
        [JsonPropertyName("students")] public List<long>? Students { get; set; }
    }

    // --- Mail models ---------------------------------------------------------

    public sealed class MailAttachment
    {
        [JsonPropertyName("itemId")] public int ItemId { get; set; }
        [JsonPropertyName("count")] public int Count { get; set; }
        [JsonPropertyName("note")] public string? Note { get; set; }
    }

    public sealed class MailRequest
    {
        [JsonPropertyName("accountId")] public long AccountId { get; set; }
        [JsonPropertyName("subject")] public string Subject { get; set; } = "System Mail";
        [JsonPropertyName("body")] public string Body { get; set; } = "";
        [JsonPropertyName("attachments")] public List<MailAttachment> Attachments { get; set; } = new();
    }

    // --- Notice models -------------------------------------------------------

    public sealed class NoticeRequest
    {
        [JsonPropertyName("title")] public string Title { get; set; } = "";
        [JsonPropertyName("text")] public string Text { get; set; } = "";
        [JsonPropertyName("startsAt")] public DateTimeOffset? StartsAt { get; set; }
        [JsonPropertyName("endsAt")] public DateTimeOffset? EndsAt { get; set; }
        [JsonPropertyName("priority")] public int Priority { get; set; } = 1;
    }
}
