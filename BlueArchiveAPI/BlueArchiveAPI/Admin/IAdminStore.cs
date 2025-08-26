// BlueArchiveAPI/Admin/IAdminStore.cs
using System.Text.Json.Nodes;
using BlueArchiveAPI.Gateway.Services;

namespace BlueArchiveAPI.Admin
{
    public interface IAdminStore
    {
        Task<AccountSnapshot?> GetAccountAsync(long accountId, CancellationToken ct = default);
        Task SaveAccountAsync(AccountSnapshot snapshot, CancellationToken ct = default);

        // Handy helper that AdminModule may call for PATCH-like updates
        Task<bool> PatchAccountAsync(long accountId, JsonObject patch, CancellationToken ct = default);
    }
}
