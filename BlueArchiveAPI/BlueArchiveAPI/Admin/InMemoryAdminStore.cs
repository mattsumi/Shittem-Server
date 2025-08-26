// BlueArchiveAPI/Admin/InMemoryAdminStore.cs
using System.Collections.Concurrent;
using System.Text.Json.Nodes;
using BlueArchiveAPI.Catalog;
using BlueArchiveAPI.Gateway.Services;

namespace BlueArchiveAPI.Admin;

public sealed class InMemoryAdminStore : IAdminStore
{
    private readonly ConcurrentDictionary<long, AccountSnapshot> _accounts = new();
    private readonly EntityCatalog _catalog;

    // You can swap this for a real DB later
    public InMemoryAdminStore(EntityCatalog catalog) => _catalog = catalog;

    // New IAdminStore contract
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
}
