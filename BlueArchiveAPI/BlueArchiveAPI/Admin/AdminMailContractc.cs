using System;
using System.Collections.Generic;

namespace BlueArchiveAPI.Admin
{
    // Game-side "Key" → we convert from string type ("Currency","Item",...) to these ints
    // Known safe defaults: 2=Currency, 4=Item (covers equipment too for now)
    public enum ParcelKeyType
    {
        Currency = 2,
        Item = 4,
    }

    public sealed class MailParcelKey
    {
        public int Type { get; set; }   // numeric game "Type" (2,4,…)
        public int Id { get; set; }     // game internal id
    }

    public sealed class MailParcelInfo
    {
        public MailParcelKey Key { get; set; } = new MailParcelKey();
        public int Amount { get; set; }
        public int Multiplier { get; set; } = 10000;   // 100.00%
        public int Probability { get; set; } = 10000;  // 100.00%
    }

    // One logical "mail" to append into Mail_List
    public sealed class QueuedMail
    {
        // Optional target; null or <= 0 means "whoever logs in" (addon will fill from response)
        public int? AccountServerId { get; set; }

        // Safe default: 11 (system/reward). You can override if you want categories.
        public int Type { get; set; } = 11;

        // What the user sees; you can use localized literal text or a key like UI_MAILBOX_…
        public string Sender { get; set; } = "Schale";
        public string Comment { get; set; } = "Admin Reward";

        // UTC times; if null the server will fill sensible defaults (now, +7d)
        public DateTime? SendDateUtc { get; set; }
        public DateTime? ExpireDateUtc { get; set; }

        public List<MailParcelInfo> Parcels { get; set; } = new();
    }

    // Request from GUI to queue a mail
    public sealed class QueueMailRequest
    {
        public QueuedMail Mail { get; set; } = new();
        // If true, keep mail after injected once (good for testing); else it will be cleared after use.
        public bool Persistent { get; set; } = false;
    }

    // For addon pull
    public sealed class MailOutboxResponse
    {
        public List<QueuedMail> Mails { get; set; } = new();
        public bool Persistent { get; set; } = false; // if true, server won’t auto-clear after pull
    }
}
