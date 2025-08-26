// BlueArchiveAPI/Admin/IAdminStore.cs
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using BlueArchiveAPI.Gateway.Services;

namespace BlueArchiveAPI.Admin
{
    /// <summary>
    /// Persistence contract for Admin account snapshots.
    /// Implementations should be thread-safe.
    /// </summary>
    public interface IAdminStore
    {
        /// <summary>Get a snapshot for the given account or null if it doesn't exist.</summary>
        Task<AccountSnapshot?> GetAsync(long accountId, CancellationToken ct = default);

        /// <summary>Return all known snapshots (may be empty).</summary>
        Task<IReadOnlyList<AccountSnapshot>> GetAllAsync(CancellationToken ct = default);

        /// <summary>Create or replace the snapshot.</summary>
        Task SaveAsync(AccountSnapshot snapshot, CancellationToken ct = default);

        /// <summary>
        /// Apply a patch action to the existing snapshot (creating one if missing)
        /// and persist the result atomically.
        /// </summary>
        Task PatchAsync(long accountId, Action<AccountSnapshot> patch, CancellationToken ct = default);
    }
}
