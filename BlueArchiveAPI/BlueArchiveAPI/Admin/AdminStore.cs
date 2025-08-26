using System.Text.Json;
using System.Text.Json.Nodes;

namespace ShittimServer.Admin;

public interface IAdminStore
{
    AccountDocument GetOrCreateAccount(long accountId);
    AccountDocument GetAccount(long accountId);
    AccountDocument UpsertAccount(AccountDocument doc);
    void AppendMail(long accountId, JsonObject mailItem);
    void AppendNotice(JsonObject notice);
    JsonArray GetNotices();
    void Save();
}

public sealed class FileAdminStore : IAdminStore
{
    private readonly string _path;
    private readonly object _lock = new();
    private readonly Dictionary<long, AccountDocument> _accounts = new();
    private readonly JsonArray _notices = new();
    private readonly JsonSerializerOptions _jsonOpts = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public FileAdminStore(string rootDir)
    {
        Directory.CreateDirectory(rootDir);
        _path = Path.Combine(rootDir, "admin_store.json");
        Load();
    }

    public AccountDocument GetOrCreateAccount(long accountId)
    {
        lock (_lock)
        {
            if (!_accounts.TryGetValue(accountId, out var doc))
            {
                doc = AccountDocument.WithDefaults(accountId);
                _accounts[accountId] = doc;
                Save_NoLock();
            }
            return Clone(doc);
        }
    }

    public AccountDocument GetAccount(long accountId)
    {
        lock (_lock)
        {
            if (!_accounts.TryGetValue(accountId, out var doc))
                throw new KeyNotFoundException($"Account {accountId} not found");
            return Clone(doc);
        }
    }

    public AccountDocument UpsertAccount(AccountDocument doc)
    {
        lock (_lock)
        {
            _accounts[doc.AccountId] = Clone(doc);
            Save_NoLock();
            return Clone(doc);
        }
    }

    public void AppendMail(long accountId, JsonObject mailItem)
    {
        lock (_lock)
        {
            if (!_accounts.TryGetValue(accountId, out var doc))
                doc = GetOrCreateAccount(accountId);

            if (doc.Data["Mail"] is not JsonArray mailArr)
            {
                mailArr = new JsonArray();
                doc.Data["Mail"] = mailArr;
            }
            mailArr.Add(mailItem);
            _accounts[accountId] = doc;
            Save_NoLock();
        }
    }

    public void AppendNotice(JsonObject notice)
    {
        lock (_lock)
        {
            _notices.Add(notice);
            Save_NoLock();
        }
    }

    public JsonArray GetNotices()
    {
        lock (_lock) { return (JsonArray)_notices.DeepClone(); }
    }

    public void Save()
    {
        lock (_lock) { Save_NoLock(); }
    }

    private void Save_NoLock()
    {
        var payload = new
        {
            accounts = _accounts.Values.ToDictionary(a => a.AccountId.ToString(), a => a.Data),
            notices = _notices
        };
        File.WriteAllText(_path, JsonSerializer.Serialize(payload, _jsonOpts));
    }

    private void Load()
    {
        if (!File.Exists(_path)) return;

        var text = File.ReadAllText(_path);
        if (string.IsNullOrWhiteSpace(text)) return;

        var root = JsonNode.Parse(text)?.AsObject();
        if (root is null) return;

        var accounts = root["accounts"] as JsonObject;
        var notices = root["notices"] as JsonArray ?? new JsonArray();

        _notices.Clear();
        foreach (var n in notices) _notices.Add(n!.DeepClone());

        _accounts.Clear();
        if (accounts != null)
        {
            foreach (var kvp in accounts)
            {
                if (long.TryParse(kvp.Key, out var id) && kvp.Value is JsonObject obj)
                {
                    _accounts[id] = new AccountDocument { AccountId = id, Data = (JsonObject)obj.DeepClone() };
                }
            }
        }
    }

    private static AccountDocument Clone(AccountDocument doc)
        => new() { AccountId = doc.AccountId, Data = (JsonObject)doc.Data.DeepClone() };
}
