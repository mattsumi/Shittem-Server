// BlueArchiveAPI/Admin/FileAdminStore.cs
using System.Text.Json;
using BlueArchiveAPI.Gateway.Services;
using Microsoft.Extensions.Hosting;

namespace BlueArchiveAPI.Admin
{
    /// <summary>
    /// File-backed IAdminStore. Persists snapshots as JSON under an on-disk root.
    /// Thread-safe via a SemaphoreSlim around IO operations.
    /// </summary>
    public sealed class FileAdminStore : IAdminStore
    {
        private readonly string _root;
        private readonly SemaphoreSlim _mutex = new(1, 1);

        private static readonly JsonSerializerOptions JsonOpts = new(JsonSerializerDefaults.Web)
        {
            WriteIndented = true
        };

        // Default to AppContext.BaseDirectory/AdminData
        public FileAdminStore()
            : this(Path.Combine(AppContext.BaseDirectory, "AdminData"))
        {
        }

        // Explicit root path
        public FileAdminStore(string root)
        {
            _root = root;
            Directory.CreateDirectory(_root);
        }

        // Convenience for hosting env
        public FileAdminStore(IHostEnvironment env)
            : this(Path.Combine(env.ContentRootPath, "AdminData"))
        {
        }

        private string PathFor(long id) => Path.Combine(_root, $"{id}.json");

        public async Task<AccountSnapshot?> GetAsync(long accountId, CancellationToken ct = default)
        {
            var path = PathFor(accountId);
            if (!File.Exists(path)) return null;

            await _mutex.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                await using var fs = File.OpenRead(path);
                return await JsonSerializer.DeserializeAsync<AccountSnapshot>(fs, JsonOpts, ct)
                    .ConfigureAwait(false);
            }
            finally
            {
                _mutex.Release();
            }
        }

        public async Task<IReadOnlyList<AccountSnapshot>> GetAllAsync(CancellationToken ct = default)
        {
            var list = new List<AccountSnapshot>();
            await _mutex.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                foreach (var file in Directory.EnumerateFiles(_root, "*.json", SearchOption.TopDirectoryOnly))
                {
                    try
                    {
                        await using var fs = File.OpenRead(file);
                        var snap = await JsonSerializer.DeserializeAsync<AccountSnapshot>(fs, JsonOpts, ct)
                            .ConfigureAwait(false);
                        if (snap != null) list.Add(snap);
                    }
                    catch
                    {
                        // ignore bad files
                    }
                }
            }
            finally
            {
                _mutex.Release();
            }

            return list.AsReadOnly();
        }

        public async Task SaveAsync(AccountSnapshot snapshot, CancellationToken ct = default)
        {
            snapshot.UpdatedAt = DateTimeOffset.UtcNow;
            var path = PathFor(snapshot.AccountId);

            await _mutex.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                await using var fs = File.Create(path);
                await JsonSerializer.SerializeAsync(fs, snapshot, JsonOpts, ct).ConfigureAwait(false);
            }
            finally
            {
                _mutex.Release();
            }
        }

        public async Task PatchAsync(long accountId, Action<AccountSnapshot> patch, CancellationToken ct = default)
        {
            await _mutex.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                var snap = await GetAsync(accountId, ct).ConfigureAwait(false)
                           ?? new AccountSnapshot(accountId);
                patch(snap);
                await SaveAsync(snap, ct).ConfigureAwait(false);
            }
            finally
            {
                _mutex.Release();
            }
        }
    }
}
