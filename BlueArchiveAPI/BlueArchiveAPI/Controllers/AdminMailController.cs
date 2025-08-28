using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace BlueArchiveAPI.Admin
{
    [ApiController]
    [Route("admin/mail")]
    public sealed class AdminMailController : ControllerBase
    {
        private readonly IAdminStore _store;
        private readonly ILogger<AdminMailController> _log;

        public AdminMailController(IAdminStore store, ILogger<AdminMailController> log)
        {
            _store = store;
            _log = log;
        }

        // GUI → queue mail
        [HttpPost("queue")]
        public IActionResult Queue([FromBody] QueueMailRequest req)
        {
            if (req?.Mail == null || req.Mail.Parcels is null || req.Mail.Parcels.Count == 0)
                return BadRequest("Mail/Parcels required");

            _store.EnqueueMail(req.Mail, req.Persistent);
            _log.LogInformation("[ADMIN][MAIL] queued parcels={count}, acct={acct}, persistent={p}",
                req.Mail.Parcels.Count, req.Mail.AccountServerId, req.Persistent);
            return Ok(new { queued = true });
        }

        // Addon → pull all pending (for user)
        [HttpGet("outbox")]
        public ActionResult<MailOutboxResponse> Outbox([FromQuery] int? accountServerId)
        {
            var res = _store.PeekOutbox(accountServerId);
            _log.LogDebug("[ADMIN][MAIL] outbox peek => {count} (acct={acct}, persistent={p})",
                res.Mails.Count, accountServerId, res.Persistent);
            return Ok(res);
        }

        // Addon → clear for user (or all)
        [HttpPost("clear")]
        public IActionResult Clear([FromQuery] int? accountServerId)
        {
            _store.ClearOutbox(accountServerId);
            _log.LogInformation("[ADMIN][MAIL] cleared outbox (acct={acct})", accountServerId);
            return Ok(new { cleared = true });
        }
    }
}
