// BlueArchiveAPI/Admin/FileAdminStore.cs
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using BlueArchiveAPI.Gateway.Services;
using Microsoft.Extensions.Hosting;

namespace BlueArchiveAPI.Admin
{
    /// <summary>
    /// File-backed IAdminStore. Persists snapshots as JSON per-account and
    /// an optional mail outbox under an on-disk root.
    /// Thread-safe via a SemaphoreSlim around IO operations.
    /// </summary>
    public sealed class FileAdminStore : IAdminStore
    {
        private readonly string _root;
        private readonly string _outboxPath;
        private readonly SemaphoreSlim _mutex = new(1, 1);

        // Snapshots are stored as <root>/<accountId>.json
        private static readonly JsonSerializerOptions JsonOpts = new(JsonSerializerDefaults.Web)
        {
            WriteIndented = true
        };

        // Runtime/persistent mail outbox
        private List<QueuedMail> _outbox = new();
        private bool _outboxPersistent;

        // --------- Ctors ---------

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
            _outboxPath = Path.Combine(_root, "outbox.json");
            LoadOutbox_NoLock(); // best-effort
        }

        // Convenience for hosting env
        public FileAdminStore(IHostEnvironment env)
            : this(Path.Combine(env.ContentRootPath, "AdminData"))
        {
        }

        private string PathFor(long id) => Path.Combine(_root, $"{id}.json");

        // --------- IAdminStore: snapshots ---------

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
                    // skip outbox file if it shares extension
                    if (string.Equals(file, _outboxPath, System.StringComparison.OrdinalIgnoreCase))
                        continue;

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
            snapshot.UpdatedAt = System.DateTimeOffset.UtcNow;
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

        public async Task PatchAsync(long accountId, System.Action<AccountSnapshot> patch, CancellationToken ct = default)
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

        // --------- IAdminStore: mail outbox ---------

        public bool IsOutboxPersistent => _outboxPersistent;

        public void EnqueueMail(QueuedMail mail, bool persistent)
        {
            // normalize missing dates
            mail.SendDateUtc ??= System.DateTime.UtcNow;
            mail.ExpireDateUtc ??= System.DateTime.UtcNow.AddDays(7);

            _mutex.Wait();
            try
            {
                _outbox.Add(mail);
                _outboxPersistent = persistent;
                SaveOutbox_NoLock();
            }
            finally
            {
                _mutex.Release();
            }
        }

        public MailOutboxResponse PeekOutbox(long? accountServerId)
        {
            _mutex.Wait();
            try
            {
                IEnumerable<QueuedMail> result = _outbox;
                if (accountServerId is > 0)
                    result = result.Where(m => m.AccountServerId == null || m.AccountServerId == accountServerId);

                return new MailOutboxResponse
                {
                    Mails = result.ToList(),
                    Persistent = _outboxPersistent
                };
            }
            finally
            {
                _mutex.Release();
            }
        }

        public void ClearOutbox(long? accountServerId)
        {
            _mutex.Wait();
            try
            {
                if (accountServerId is > 0)
                {
                    _outbox = _outbox.Where(m => m.AccountServerId != accountServerId).ToList();
                }
                else
                {
                    _outbox.Clear();
                    _outboxPersistent = false;
                }
                SaveOutbox_NoLock();
            }
            finally
            {
                _mutex.Release();
            }
        }

        // --------- outbox persistence helpers ---------

        private sealed class OutboxFileModel
        {
            public List<QueuedMail> Mails { get; set; } = new();
            public bool Persistent { get; set; }
        }

        private void LoadOutbox_NoLock()
        {
            try
            {
                if (!File.Exists(_outboxPath)) return;
                var json = File.ReadAllText(_outboxPath);
                var model = JsonSerializer.Deserialize<OutboxFileModel>(json, JsonOpts);
                if (model != null)
                {
                    _outbox = model.Mails ?? new List<QueuedMail>();
                    _outboxPersistent = model.Persistent;
                }
            }
            catch
            {
                // ignore malformed file
                _outbox = new List<QueuedMail>();
                _outboxPersistent = false;
            }
        }

        private void SaveOutbox_NoLock()
        {
            try
            {
                var model = new OutboxFileModel { Mails = _outbox, Persistent = _outboxPersistent };
                File.WriteAllText(_outboxPath, JsonSerializer.Serialize(model, JsonOpts));
            }
            catch
            {
                // swallow IO errors; this is best-effort persistence
            }
        }
    }
}
