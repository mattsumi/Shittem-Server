// BlueArchiveAPI/Gateway/Services/AccountSnapshot.cs
using System;
using System.Text.Json.Nodes;

namespace BlueArchiveAPI.Gateway.Services
{
    /// <summary>
    /// Snapshot of account data used by ProtocolRouter/Admin.
    /// </summary>
    public sealed class AccountSnapshot
    {
        public long AccountId { get; init; }

        // Fields referenced in ProtocolRouter.cs (nullable to reflect "may not be present" semantics)
        public string? Nickname { get; set; }
        public int? Level { get; set; }
        public int? PaidPyroxene { get; set; }
        public int? FreePyroxene { get; set; }
        public int? Pyroxene { get; set; } // some logs print this directly
        public int? Credits { get; set; }

        public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;

        // Arbitrary admin JSON (safe place to stash extra flags)
        public JsonObject Data { get; init; } = new JsonObject();

        public AccountSnapshot()
        {
            UpdatedAt = DateTimeOffset.UtcNow;
        }

        public AccountSnapshot(long accountId) : this(accountId, new JsonObject())
        {
        }

        // Required by InMemoryAdminStore usage
        public AccountSnapshot(long accountId, JsonObject data)
        {
            AccountId = accountId;
            Data = data ?? new JsonObject();
            UpdatedAt = DateTimeOffset.UtcNow;
        }
    }
}
