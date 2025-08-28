using BlueArchiveAPI.Catalog;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace BlueArchiveAPI.Controllers
{
    [ApiController]
    [Route("admin/catalog")]
    public sealed class AdminCatalogController : ControllerBase
    {
        private readonly IEntityCatalog _catalog;
        private readonly ILogger<AdminCatalogController> _logger;

        public AdminCatalogController(IEntityCatalog catalog, ILogger<AdminCatalogController> logger)
        {
            _catalog = catalog;
            _logger = logger;
        }

        // Support both modern and legacy routes via shims:
        // - GET /admin/catalog/types
        // - GET /admin/catalog            (no params) => types
        // - GET /admin/catalog?type=Item  (query)     => entities
        // - GET ~/admin/items/types
        // - GET ~/admin/items?type=Item
        [HttpGet]
        [HttpGet("types")]
        [HttpGet("~/admin/items")]
        [HttpGet("~/admin/items/types")]
        public async Task<IActionResult> Get([FromQuery] string? type, CancellationToken ct)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(type))
                {
                    var types = _catalog.GetTypes() ?? Array.Empty<string>();
                    _logger.LogInformation("[ADMIN][CATALOG] types={Count}", types.Count);
                    return Ok(types);
                }

                var canonical = CanonicalizeType(type!);
                if (string.IsNullOrWhiteSpace(canonical))
                {
                    _logger.LogInformation("[ADMIN][CATALOG] unknown type '{Type}', returning empty", type);
                    return Ok(Array.Empty<EntityDto>());
                }

                var list = await _catalog.GetEntitiesAsync(canonical, ct).ConfigureAwait(false);
                _logger.LogInformation("[ADMIN][CATALOG] {Type} entities={Count}", canonical, list.Count);
                return Ok(list ?? Array.Empty<EntityDto>());
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[ADMIN][CATALOG] error in Get: {Message}", ex.Message);
                return Ok(Array.Empty<object>());
            }
        }

        // GET /admin/catalog/{type}
        [HttpGet("{type}")]
        public async Task<IActionResult> GetByPath([FromRoute] string type, CancellationToken ct)
        {
            try
            {
                var canonical = CanonicalizeType(type);
                if (string.IsNullOrWhiteSpace(canonical))
                {
                    _logger.LogInformation("[ADMIN][CATALOG] unknown type '{Type}', returning empty", type);
                    return Ok(Array.Empty<EntityDto>());
                }

                var list = await _catalog.GetEntitiesAsync(canonical, ct).ConfigureAwait(false);
                _logger.LogInformation("[ADMIN][CATALOG] {Type} entities={Count}", canonical, list.Count);
                return Ok(list ?? Array.Empty<EntityDto>());
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[ADMIN][CATALOG] error in GetByPath: {Message}", ex.Message);
                return Ok(Array.Empty<object>());
            }
        }

        // POST /admin/catalog/rebuild
        [HttpPost("rebuild")]
        public IActionResult Rebuild()
        {
            _logger.LogInformation("[ADMIN][CATALOG] Rebuild endpoint is obsolete and does nothing.");
            return Ok(new { rebuilt = 0, message = "This endpoint is obsolete and no longer functional." });
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