// BlueArchiveAPI/Admin/InMemoryAdminStore.cs
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Text.Json.Nodes;
using BlueArchiveAPI.Catalog;
using BlueArchiveAPI.Gateway.Services;

namespace BlueArchiveAPI.Admin;

public sealed class InMemoryAdminStore : IAdminStore
{
    private readonly ConcurrentDictionary<long, AccountSnapshot> _accounts = new();
    private readonly IEntityCatalog _catalog;

    // Mail outbox (runtime)
    private readonly ConcurrentBag<QueuedMail> _mailOutbox = new();
    private volatile bool _outboxPersistent = false;

    public bool IsOutboxPersistent => _outboxPersistent;

    // You can swap this for a real DB later
    public InMemoryAdminStore(IEntityCatalog catalog) => _catalog = catalog;

    // ---------------------------
    // IAdminStore: snapshots
    // ---------------------------

    public Task<AccountSnapshot?> GetAsync(long accountId, CancellationToken ct = default)
        => Task.FromResult(_accounts.TryGetValue(accountId, out var snap) ? snap : null);

    public Task<IReadOnlyList<AccountSnapshot>> GetAllAsync(CancellationToken ct = default)
        => Task.FromResult<IReadOnlyList<AccountSnapshot>>(_accounts.Values.ToList().AsReadOnly());

    public Task SaveAsync(AccountSnapshot snapshot, CancellationToken ct = default)
    {
        _accounts[snapshot.AccountId] = snapshot;
        return Task.CompletedTask;
    }

    public Task PatchAsync(long accountId, Action<AccountSnapshot> patch, CancellationToken ct = default)
    {
        var snap = _accounts.GetOrAdd(accountId, id => new AccountSnapshot(id, new JsonObject()));
        patch(snap);
        _accounts[accountId] = snap;
        return Task.CompletedTask;
    }

    // Convenience helpers kept for callers that still pass raw JSON patches
    public Task<bool> PatchAccountAsync(long accountId, JsonObject patch, CancellationToken ct = default)
    {
        if (!_accounts.TryGetValue(accountId, out var snap)) return Task.FromResult(false);
        foreach (var kv in patch) snap.Data[kv.Key] = kv.Value;
        return Task.FromResult(true);
    }

    // Extra utilities used by admin/handlers (not part of the interface)
    public Task<IReadOnlyList<(int Id, string Name)>> LookupAsync(EntityType type, string query, int limit = 50, CancellationToken ct = default)
    {
        var rows = _catalog.Search(type, query, limit)
            .Select(e => (e.Id, e.CanonicalName))
            .ToList()
            .AsReadOnly();
        return Task.FromResult<IReadOnlyList<(int, string)>>(rows);
    }

    public Task SetNextGachaAsync(long accountId, IReadOnlyList<int> studentIds, CancellationToken ct = default)
    {
        // Stash it under admin-only key; ProtocolRouter can read & consume it.
        var snap = _accounts.GetOrAdd(accountId, id => new AccountSnapshot(id, new JsonObject()));
        snap.Data["nextGachaStudentIds"] = new JsonArray(studentIds.Select(i => (JsonNode)i).ToArray());
        return Task.CompletedTask;
    }

    // ---------------------------
    // IAdminStore: mail outbox
    // ---------------------------

    public void EnqueueMail(QueuedMail mail, bool persistent)
    {
        if (mail.SendDateUtc == null) mail.SendDateUtc = System.DateTime.UtcNow;
        if (mail.ExpireDateUtc == null) mail.ExpireDateUtc = System.DateTime.UtcNow.AddDays(7);
        _mailOutbox.Add(mail);
        _outboxPersistent = persistent;
    }

    public MailOutboxResponse PeekOutbox(long? accountServerId)
    {
        var all = _mailOutbox.ToArray();
        List<QueuedMail> filtered = accountServerId is > 0
            ? all.Where(m => m.AccountServerId == null || m.AccountServerId == accountServerId).ToList()
            : all.ToList();

        return new MailOutboxResponse { Mails = filtered, Persistent = _outboxPersistent };
    }

    public void ClearOutbox(long? accountServerId)
    {
        if (accountServerId is not > 0)
        {
            while (_mailOutbox.TryTake(out _)) { }
            _outboxPersistent = false;
            return;
        }

        var keep = new List<QueuedMail>();
        while (_mailOutbox.TryTake(out var m))
        {
            if (m.AccountServerId != null && m.AccountServerId != accountServerId)
                keep.Add(m);
        }
        foreach (var m in keep) _mailOutbox.Add(m);
    }
}
