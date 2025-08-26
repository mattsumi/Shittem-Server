// AdminStore.cs
using System.Collections.Concurrent;
using System.Text.Json.Nodes;

namespace ShittimServer.Admin
{
    /// <summary>
    /// Extremely small in-memory admin backing store. This gives the GUI something stable to
    /// talk to while the gateway evolves. It can later be swapped for real persistence.
    /// </summary>
    public sealed class AdminStore
    {
        private readonly ConcurrentDictionary<long, AccountSummary> _accounts = new();
        private readonly ConcurrentBag<NoticeRequest> _notices = new();

        // --- Accounts --------------------------------------------------------

        public AccountSummary GetOrCreateAccount(long accountId)
            => _accounts.GetOrAdd(accountId, id => new AccountSummary { AccountId = id });

        public bool TryGetAccount(long accountId, out AccountSummary acc)
            => _accounts.TryGetValue(accountId, out acc!);

        public AccountSummary ApplyPatch(long accountId, AccountPatch patch)
        {
            var acc = GetOrCreateAccount(accountId);

            if (patch.Nickname is { Length: > 0 }) acc.Nickname = patch.Nickname!;
            if (patch.Level.HasValue) acc.Level = Math.Max(1, patch.Level.Value);
            if (patch.Pyroxene.HasValue) acc.Pyroxene = Math.Max(0, patch.Pyroxene.Value);
            if (patch.Credits.HasValue) acc.Credits = Math.Max(0, patch.Credits.Value);

            if (patch.Inventory is not null)
            {
                foreach (var kv in patch.Inventory)
                    acc.Inventory[kv.Key] = kv.Value;
            }
            if (patch.Students is not null)
            {
                acc.Students = patch.Students.Distinct().ToList();
            }
            _accounts[accountId] = acc;
            return acc;
        }

        /// <summary>
        /// Capture authoritative account fields from official gateway responses.
        /// Call this from the ProtocolRouter after a successful handler executes.
        /// </summary>
        public void CaptureFromOfficial(long accountId, JsonObject payload)
        {
            var acc = GetOrCreateAccount(accountId);

            // Heuristic: look for common official keys (will be refined as we capture)
            if (payload.TryGetPropertyValue("AccountLevel", out var lvlNode) && lvlNode is not null && int.TryParse(lvlNode.ToString(), out var lvl))
                acc.Level = Math.Max(1, lvl);

            if (payload.TryGetPropertyValue("Gem", out var gemNode) && gemNode is not null && int.TryParse(gemNode.ToString(), out var gem))
                acc.Pyroxene = Math.Max(0, gem);

            if (payload.TryGetPropertyValue("Credit", out var crNode) && crNode is not null && int.TryParse(crNode.ToString(), out var cr))
                acc.Credits = Math.Max(0, cr);

            if (payload.TryGetPropertyValue("Nickname", out var nnNode) && nnNode is not null)
                acc.Nickname = nnNode.ToString();

            _accounts[accountId] = acc;
        }

        // --- Notices ---------------------------------------------------------

        public NoticeRequest AddNotice(NoticeRequest n)
        {
            _notices.Add(n);
            return n;
        }

        public IReadOnlyCollection<NoticeRequest> ListNotices() => _notices.ToArray();

        // --- Mail ------------------------------------------------------------

        // Stub: just echo back. Plug into your game's real mail sender later.
        public object SendMail(MailRequest req) =>
            new
            {
                delivered = true,
                to = req.AccountId,
                subject = req.Subject,
                attachments = req.Attachments,
            };

        // --- Status -----------------------------------------------------------

        public object Status() => new
        {
            accounts = _accounts.Count,
            notices = _notices.Count
        };
    }
}
