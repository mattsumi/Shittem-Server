// BlueArchiveAPI/Admin/IAdminStore.cs
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using BlueArchiveAPI.Gateway.Services;

namespace BlueArchiveAPI.Admin
{
    /// <summary>
    /// Persistence contract for Admin account snapshots and admin runtime queues.
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

        // ---------------------------
        // Admin Mail Outbox (runtime)
        // ---------------------------

        /// <summary>
        /// Enqueue a mail to be injected into the next Mail_List response.
        /// If <paramref name="persistent"/> is true, items remain after injection until cleared.
        /// </summary>
        void EnqueueMail(QueuedMail mail, bool persistent);

        /// <summary>
        /// Peek the current outbox, optionally filtered to an account id.
        /// </summary>
        MailOutboxResponse PeekOutbox(long? accountServerId);

        /// <summary>
        /// Clear the outbox for a specific account or, if null, clear all.
        /// </summary>
        void ClearOutbox(long? accountServerId);

        /// <summary>
        /// True if the outbox is marked persistent (will not auto-clear on use).
        /// </summary>
        bool IsOutboxPersistent { get; }
    }
}
