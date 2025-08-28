using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Serilog;

namespace BlueArchiveAPI.Catalog
{
    public sealed class EntityCatalog : IEntityCatalog
    {
        private readonly string _dataDir;
        private readonly string _lang;
        private readonly Dictionary<string, List<EntityDto>> _byType = new(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> _types = new(StringComparer.OrdinalIgnoreCase);
        private readonly FileSystemWatcher? _watcher;

        public EntityCatalog(string dataDir, string lang = "en")
        {
            _dataDir = dataDir;
            _lang = lang;
            LoadAll();

            if (Directory.Exists(Path.Combine(_dataDir, _lang)))
            {
                _watcher = new FileSystemWatcher(Path.Combine(_dataDir, _lang), "*.json")
                {
                    NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.FileName
                };
                _watcher.Changed += OnChanged;
                _watcher.Created += OnChanged;
                _watcher.Deleted += OnChanged;
                _watcher.Renamed += OnRenamed;
                _watcher.EnableRaisingEvents = true;
            }
        }

        private void OnRenamed(object sender, RenamedEventArgs e)
        {
            Log.Information("[CATALOG] reload due to file rename: {File}", e.FullPath);
            LoadAll();
        }

        private void OnChanged(object sender, FileSystemEventArgs e)
        {
            Log.Information("[CATALOG] reload due to file change: {File}", e.FullPath);
            LoadAll();
        }

        private void LoadAll()
        {
            lock (this)
            {
                var loadedCounts = new Dictionary<string, int>();

                LoadStudents("Student", Path.Combine(_dataDir, _lang, "students.json"), loadedCounts);
                LoadItems("Item", Path.Combine(_dataDir, _lang, "items.json"), loadedCounts);
                LoadCurrency("Currency", Path.Combine(_dataDir, _lang, "currency.json"), loadedCounts);
                LoadGeneric("Weapon", Path.Combine(_dataDir, _lang, "weapons.json"), loadedCounts);
                LoadGeneric("Gear", Path.Combine(_dataDir, _lang, "equipment.json"), loadedCounts);

                _types.Clear();
                foreach (var key in _byType.Keys)
                {
                    if (_byType.TryGetValue(key, out var list) && list.Count > 0)
                        _types.Add(key);
                }

                var counts = string.Join(", ", loadedCounts.Select(kvp => $"{kvp.Key}={kvp.Value}"));
                Log.Information("[CATALOG] loaded: " + counts);
            }
        }

        private void LoadCurrency(string type, string path, Dictionary<string, int> loadedCounts)
        {
            var list = new List<EntityDto>();
            if (!File.Exists(path))
            {
                Log.Warning("[CATALOG] {Type} file not found or empty: {Path}", type, path);
                loadedCounts[type] = 0;
                _byType[type] = list;
                return;
            }

            try
            {
                var json = File.ReadAllText(path);
                var entities = JsonSerializer.Deserialize<JsonElement[]>(json);

                if (entities != null)
                {
                    foreach (var entity in entities)
                    {
                        if (entity.TryGetProperty("Id", out var idElement) && idElement.ValueKind == JsonValueKind.Number)
                        {
                            var id = idElement.GetInt64().ToString();
                            string name = (entity.TryGetProperty("Name", out var nameElement) && nameElement.ValueKind == JsonValueKind.String ? nameElement.GetString() : null)
                                ?? (entity.TryGetProperty("DisplayName", out var dnElement) && dnElement.ValueKind == JsonValueKind.String ? dnElement.GetString() : null)
                                ?? (entity.TryGetProperty("EnglishName", out var enElement) && enElement.ValueKind == JsonValueKind.String ? enElement.GetString() : null)
                                ?? $"Currency #{id}";

                            list.Add(new EntityDto { Id = id, Name = name });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[CATALOG] Failed to load {Type} from {Path}", type, path);
            }

            _byType[type] = list.OrderBy(e => e.Name, StringComparer.OrdinalIgnoreCase).ToList();
            loadedCounts[type] = list.Count;
        }

        private void LoadStudents(string type, string path, Dictionary<string, int> loadedCounts)
        {
            var list = new List<EntityDto>();
            if (!File.Exists(path))
            {
                Log.Warning("[CATALOG] {Type} file not found or empty: {Path}", type, path);
                loadedCounts[type] = 0;
                _byType[type] = list;
                return;
            }

            try
            {
                var json = File.ReadAllText(path);
                var entities = JsonSerializer.Deserialize<JsonElement[]>(json);

                if (entities != null)
                {
                    foreach (var entity in entities)
                    {
                        if (entity.TryGetProperty("Id", out var idElement) && idElement.ValueKind == JsonValueKind.Number)
                        {
                            var id = idElement.GetInt64().ToString();
                            string name = (entity.TryGetProperty("Name", out var nameElement) ? nameElement.GetString() : null)
                                ?? (entity.TryGetProperty("NameEN", out var nameEnElement) ? nameEnElement.GetString() : null)
                                ?? (entity.TryGetProperty("NameEn", out var nameEn2Element) ? nameEn2Element.GetString() : null)
                                ?? $"Student #{id}";

                            list.Add(new EntityDto { Id = id, Name = name });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[CATALOG] Failed to load {Type} from {Path}", type, path);
            }

            _byType[type] = list.OrderBy(e => e.Name, StringComparer.OrdinalIgnoreCase).ToList();
            loadedCounts[type] = list.Count;
        }

        private void LoadItems(string type, string path, Dictionary<string, int> loadedCounts)
        {
            var items = new List<EntityDto>();

            if (!File.Exists(path))
            {
                Log.Warning("[CATALOG] {Type} file not found or empty: {Path}", type, path);
                loadedCounts[type] = 0;
                _byType[type] = items;
                return;
            }

            try
            {
                var json = File.ReadAllText(path);
                var entities = JsonSerializer.Deserialize<JsonElement[]>(json);

                if (entities != null)
                {
                    foreach (var entity in entities)
                    {
                        if (entity.TryGetProperty("IsCurrency", out var isCurrencyElement) && isCurrencyElement.ValueKind == JsonValueKind.True)
                        {
                            continue;
                        }
                        
                        if (entity.TryGetProperty("Id", out var idElement) && idElement.ValueKind == JsonValueKind.Number)
                        {
                            var id = idElement.GetInt64().ToString();
                            string name = (entity.TryGetProperty("Name", out var nameElement) ? nameElement.GetString() : null)
                                ?? (entity.TryGetProperty("NameEN", out var nameEnElement) ? nameEnElement.GetString() : null)
                                ?? $"Entity #{id}";

                            var dto = new EntityDto { Id = id, Name = name };
                            items.Add(dto);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[CATALOG] Failed to load {Type} from {Path}", type, path);
            }

            _byType[type] = items.OrderBy(e => e.Name, StringComparer.OrdinalIgnoreCase).ToList();
            loadedCounts[type] = items.Count;
        }

        private void LoadGeneric(string type, string path, Dictionary<string, int> loadedCounts)
        {
            var list = new List<EntityDto>();
            if (!File.Exists(path))
            {
                Log.Warning("[CATALOG] {Type} file not found or empty: {Path}", type, path);
                loadedCounts[type] = 0;
                _byType[type] = list;
                return;
            }

            try
            {
                var json = File.ReadAllText(path);
                var entities = JsonSerializer.Deserialize<JsonElement[]>(json);

                if (entities != null)
                {
                    foreach (var entity in entities)
                    {
                        if (entity.TryGetProperty("Id", out var idElement) && idElement.ValueKind == JsonValueKind.Number)
                        {
                            var id = idElement.GetInt64().ToString();
                            string name = (entity.TryGetProperty("Name", out var nameElement) ? nameElement.GetString() : null)
                                ?? $"{type} #{id}";

                            list.Add(new EntityDto { Id = id, Name = name });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log.Error(ex, "[CATALOG] Failed to load {Type} from {Path}", type, path);
            }

            _byType[type] = list.OrderBy(e => e.Name, StringComparer.OrdinalIgnoreCase).ToList();
            loadedCounts[type] = list.Count;
        }

        public IReadOnlyList<string> GetTypes()
        {
            return _types.OrderBy(t => t, StringComparer.OrdinalIgnoreCase).ToList();
        }

        public Task<IReadOnlyList<EntityDto>> GetEntitiesAsync(string type, CancellationToken ct = default)
        {
            var canonical = CanonicalizeType(type);
            if (_byType.TryGetValue(canonical, out var entities))
            {
                return Task.FromResult<IReadOnlyList<EntityDto>>(new List<EntityDto>(entities));
            }
            return Task.FromResult<IReadOnlyList<EntityDto>>(Array.Empty<EntityDto>());
        }

        public bool TryGetById(EntityType type, int id, [NotNullWhen(true)] out Entity? entity)
        {
            entity = null;
            return false;
        }

        public bool TryGetIdByName(EntityType type, string nameOrAlias, out int id)
        {
            id = 0;
            return false;
        }

        public IEnumerable<Entity> Search(EntityType type, string query, int limit = 20)
        {
            return Array.Empty<Entity>();
        }

        private static string CanonicalizeType(string input)
        {
            var key = (input ?? "").Trim().ToLowerInvariant();
            return key switch
            {
                "student" or "students" or "character" or "characters" or "unit" or "units" => "Student",
                "item" or "items" => "Item",
                "currency" or "currencies" => "Currency",
                "weapon" or "weapons" => "Weapon",
                "gear" or "gears" => "Gear",
                "gachagroup" or "gacha group" or "gacha-group" or "gacha_groups" or "gacha-groups" or "gachagroups" => "GachaGroup",
                _ => input?.Trim() ?? ""
            };
        }
    }
}
