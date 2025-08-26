using Microsoft.Data.Sqlite;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace BlueArchiveAPI.Catalog;

public sealed class EntityCatalog : IEntityCatalog
{
    private readonly Dictionary<(EntityType, int), Entity> _byId = new();
    private readonly Dictionary<(EntityType, string), Entity> _bySlug = new();
    private readonly Dictionary<EntityType, List<Entity>> _byType = new();

    /// <summary>
    /// Empty ctor kept private to ensure we always load via a path or connection.
    /// </summary>
    private EntityCatalog() { }

    /// <summary>
    /// NEW: Construct a catalog directly from a SQLite file path.
    /// </summary>
    public EntityCatalog(string sqlitePath)
    {
        if (!File.Exists(sqlitePath))
            throw new FileNotFoundException($"catalog.sqlite not found at {sqlitePath}");

        // Open read-only with shared cache so multiple readers can coexist.
        var csb = new SqliteConnectionStringBuilder
        {
            DataSource = sqlitePath,
            Mode = SqliteOpenMode.ReadOnly,
            Cache = SqliteCacheMode.Shared
        };

        using var cn = new SqliteConnection(csb.ToString());
        cn.Open();
        LoadCore(cn);
    }

    /// <summary>
    /// NEW: Construct a catalog from an already-open SqliteConnection.
    /// The connection is not disposed by this class.
    /// </summary>
    public EntityCatalog(SqliteConnection connection)
    {
        if (connection.State != System.Data.ConnectionState.Open)
            connection.Open();
        LoadCore(connection);
    }

    /// <summary>
    /// Back-compat helper: load from path (now just calls the new ctor).
    /// </summary>
    public static EntityCatalog LoadFrom(string sqlitePath) => new EntityCatalog(sqlitePath);

    /// <summary>
    /// Core loader that fills in-memory indices from the provided open connection.
    /// </summary>
    private void LoadCore(SqliteConnection cn)
    {
        // Load entities
        using (var cmd = cn.CreateCommand())
        {
            cmd.CommandText = @"SELECT entity_type, entity_id, canonical_name, dev_name, rarity, meta_json FROM entity";
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                var type = (EntityType)r.GetInt32(0);
                var id = r.GetInt32(1);
                var name = r.GetString(2);
                var dev = r.IsDBNull(3) ? null : r.GetString(3);
                int? rarity = r.IsDBNull(4) ? null : r.GetInt32(4);
                var metaRaw = r.IsDBNull(5) ? "{}" : r.GetString(5);
                var meta = JsonNode.Parse(metaRaw)?.AsObject() ?? new JsonObject();

                var e = new Entity
                {
                    Type = type,
                    Id = id,
                    CanonicalName = name,
                    DevName = dev,
                    Rarity = rarity,
                    Meta = meta
                };

                _byId[(type, id)] = e;
                if (!_byType.TryGetValue(type, out var list))
                    _byType[type] = list = new List<Entity>();
                list.Add(e);

                _bySlug[(type, Slug(name))] = e;
                if (!string.IsNullOrWhiteSpace(dev))
                    _bySlug[(type, Slug(dev!))] = e;
            }
        }

        // Load aliases
        using (var cmd = cn.CreateCommand())
        {
            cmd.CommandText = @"SELECT entity_type, entity_id, alias_slug FROM entity_alias";
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                var type = (EntityType)r.GetInt32(0);
                var id = r.GetInt32(1);
                var slug = r.GetString(2);

                if (_byId.TryGetValue((type, id), out var e))
                {
                    var key = (type, slug);
                    if (!_bySlug.ContainsKey(key))
                        _bySlug[key] = e;
                }
            }
        }
    }

    public bool TryGetById(EntityType type, int id, out Entity entity)
        => _byId.TryGetValue((type, id), out entity!);

    public bool TryGetIdByName(EntityType type, string nameOrAlias, out int id)
    {
        var slug = Slug(nameOrAlias);
        if (_bySlug.TryGetValue((type, slug), out var e))
        {
            id = e.Id;
            return true;
        }
        id = 0;
        return false;
    }

    public IEnumerable<Entity> Search(EntityType type, string query, int limit = 20)
    {
        query = (query ?? "").Trim();
        if (string.IsNullOrEmpty(query)) return Array.Empty<Entity>();
        var q = Slug(query);

        if (!_byType.TryGetValue(type, out var list))
            return Array.Empty<Entity>();

        // naive slug/substring match over canonical + dev
        return list
            .Select(e => new
            {
                E = e,
                Score =
                    (Slug(e.CanonicalName).Contains(q) ? 2 : 0) +
                    (!string.IsNullOrWhiteSpace(e.DevName) && Slug(e.DevName!).Contains(q) ? 1 : 0)
            })
            .Where(x => x.Score > 0)
            .OrderByDescending(x => x.Score)
            .ThenBy(x => x.E.CanonicalName)
            .Take(limit)
            .Select(x => x.E);
    }

    private static string Slug(string s)
    {
        // Remove diacritics
        var norm = s.Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder(norm.Length);
        foreach (var ch in norm)
        {
            var uc = System.Globalization.CharUnicodeInfo.GetUnicodeCategory(ch);
            if (uc != System.Globalization.UnicodeCategory.NonSpacingMark)
                sb.Append(ch);
        }
        var ascii = sb.ToString().Normalize(NormalizationForm.FormC).ToLowerInvariant();

        // Replace non-alnum runs with single '-'
        var outSb = new StringBuilder(ascii.Length);
        bool lastDash = false;
        foreach (var ch in ascii)
        {
            if (char.IsLetterOrDigit(ch)) { outSb.Append(ch); lastDash = false; }
            else { if (!lastDash) { outSb.Append('-'); lastDash = true; } }
        }
        var slug = outSb.ToString().Trim('-');
        while (slug.Contains("--")) slug = slug.Replace("--", "-");
        return slug;
    }
}
