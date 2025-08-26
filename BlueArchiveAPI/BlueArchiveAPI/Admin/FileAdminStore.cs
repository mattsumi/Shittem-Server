// BlueArchiveAPI/Admin/FileAdminStore.cs
using System.Text.Json;
using System.Text.Json.Nodes;
using BlueArchiveAPI.Gateway.Services;
using Microsoft.Extensions.Hosting;

namespace BlueArchiveAPI.Admin
{
    /// <summary>
    /// Very simple file-backed store so the project compiles and runs.
    /// Writes JSON per-account into ./AdminData/{accountId}.json
    /// Swap for your real persistence later.
    /// </summary>
    public sealed class FileAdminStore : IAdminStore
    {
        private readonly string _root;
        private static readonly JsonSerializerOptions JsonOpts = new(JsonSerializerDefaults.Web)
        {
            WriteIndented = true
        };

        public FileAdminStore(IHostEnvironment env)
        {
            _root = Path.Combine(env.ContentRootPath, "AdminData");
            Directory.CreateDirectory(_root);
        }

        private string PathFor(long id) => System.IO.Path.Combine(_root, $"{id}.json");

        public async Task<AccountSnapshot?> GetAccountAsync(long accountId, CancellationToken ct = default)
        {
            var path = PathFor(accountId);
            if (!File.Exists(path)) return null;

            await using var fs = File.OpenRead(path);
            return await JsonSerializer.DeserializeAsync<AccountSnapshot>(fs, JsonOpts, ct);
        }

        public async Task SaveAccountAsync(AccountSnapshot snapshot, CancellationToken ct = default)
        {
            snapshot.UpdatedAt = DateTimeOffset.UtcNow;

            var path = PathFor(snapshot.AccountId);
            await using var fs = File.Create(path);
            await JsonSerializer.SerializeAsync(fs, snapshot, JsonOpts, ct);
        }

        public async Task<bool> PatchAccountAsync(long accountId, JsonObject patch, CancellationToken ct = default)
        {
            var snap = await GetAccountAsync(accountId, ct) ?? new AccountSnapshot { AccountId = accountId };
            foreach (var kv in patch)
                snap.Data[kv.Key] = kv.Value;
            await SaveAccountAsync(snap, ct);
            return true;
        }
    }
}
