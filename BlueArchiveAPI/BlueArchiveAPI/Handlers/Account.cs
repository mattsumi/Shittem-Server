using BlueArchiveAPI.NetworkModels;
using Newtonsoft.Json;
using System.Security.Cryptography;
using System.Text;

namespace BlueArchiveAPI.Handlers
{
    public static class Account
    {
        /// <summary>
        /// Generates a deterministic MxToken based on DevId and AccountId
        /// </summary>
        public static string GenerateMxToken(string devId, long accountId)
        {
            if (string.IsNullOrEmpty(devId))
                devId = "DefaultDevId";
                
            // Create deterministic seed from DevId and AccountId
            var seed = $"{devId}:{accountId}".GetHashCode();
            var random = new Random(seed);
            
            // Generate 32 bytes deterministically
            var tokenBytes = new byte[32];
            random.NextBytes(tokenBytes);
            
            return Convert.ToBase64String(tokenBytes);
        }
        
        /// <summary>
        /// Generates an AuthToken based on MxToken and AccountId (mimics client generation)
        /// </summary>
        public static string GenerateAuthToken(string mxToken, long accountId)
        {
            if (string.IsNullOrEmpty(mxToken))
                return string.Empty;
                
            // Create a deterministic auth token using HMAC-SHA256
            var key = Encoding.UTF8.GetBytes($"AuthKey_{accountId}");
            var data = Encoding.UTF8.GetBytes(mxToken);
            
            using (var hmac = new HMACSHA256(key))
            {
                var hash = hmac.ComputeHash(data);
                return Convert.ToBase64String(hash);
            }
        }
        
        /// <summary>
        /// Gets session data from the current context or generates defaults
        /// </summary>
        private static (long accountId, int accountServerId, string mxToken) GetSessionData(string? devId = null)
        {
            // Generate deterministic data based on devId for consistent behavior
            var seed = devId?.GetHashCode() ?? "DefaultSession".GetHashCode();
            var random = new Random(Math.Abs(seed));
            
            var accountId = 1000000 + random.Next(1, 999999);
            var accountServerId = random.Next(1, 10);
            var mxToken = GenerateMxToken(devId ?? "DefaultDevId", accountId);
            
            return (accountId, accountServerId, mxToken);
        }

        public class CheckNexon : BaseHandler<AccountCheckNexonRequest, AccountCheckNexonResponse>
        {
            protected override async Task<AccountCheckNexonResponse> Handle(AccountCheckNexonRequest request)
            {
                // Generate consistent session data instead of hardcoded values
                var (accountId, accountServerId, mxToken) = GetSessionData();

                var session = new SessionKey
                {
                    AccountServerId = accountServerId,
                    MxToken = mxToken
                };

                return new AccountCheckNexonResponse
                {
                    ResultState = 1,
                    AccountId = accountId,
                    SessionKey = session
                };
            }
        }
        public class LoginSync : BaseHandler<AccountLoginSyncRequest, AccountLoginSyncResponse>
        {
            protected override async Task<AccountLoginSyncResponse> Handle(AccountLoginSyncRequest request)
            {
                var result = Utils.GetDataFromFile<AccountLoginSyncResponse>("Data/account.loginsync", false);
                
                if (result != null)
                {
                    result.AccountCurrencySyncResponse.AccountCurrencyDB.CurrencyDict[CurrencyTypes.Gem] = 99999999;
                    result.AccountCurrencySyncResponse.AccountCurrencyDB.CurrencyDict[CurrencyTypes.GemBonus] = 99999999;
                    return result;
                }
                
                // Return default response if file doesn't exist
                return new AccountLoginSyncResponse();
            }
        }

        public class GetTutorial : BaseHandler<AccountGetTutorialRequest, AccountGetTutorialResponse>
        {
            protected override async Task<AccountGetTutorialResponse> Handle(AccountGetTutorialRequest request)
            {
                return new AccountGetTutorialResponse
                {
                    TutorialIds = new List<long> { 1, 2, 3, 4, 5 }
                };
            }
        }

        public class SetTutorial : BaseHandler<AccountSetTutorialRequest, AccountSetTutorialResponse>
        {
            protected override async Task<AccountSetTutorialResponse> Handle(AccountSetTutorialRequest request)
            {
                return new AccountSetTutorialResponse();
            }
        }

        public class Auth : BaseHandler<AccountAuthRequest, AccountAuthResponse>
        {
            protected override async Task<AccountAuthResponse> Handle(AccountAuthRequest request)
            {
                // Generate consistent session data based on device info
                var devId = request.DevId ?? "DefaultDevId";
                var (accountId, accountServerId, mxToken) = GetSessionData(devId);
                
                // Generate AuthToken based on MxToken and AccountId
                var authToken = GenerateAuthToken(mxToken, accountId);
                
                // Create SessionKey with proper data
                var sessionKey = new SessionKey
                {
                    AccountServerId = accountServerId,
                    MxToken = mxToken
                };

                return new AccountAuthResponse
                {
                    SessionKey = sessionKey,
                    EncryptedUID = authToken,
                    AccountDB = new AccountDB
                    {
                        ServerId = accountId,
                        Nickname = "佑树",
                        CallNameKatakana = string.Empty,
                        State = AccountState.Normal,
                        Level = 100,
                        RepresentCharacterServerId = 89919579,
                        PublisherAccountId = accountServerId,
                    },
                    AttendanceBookRewards = new List<AttendanceBookReward>(),
                    RepurchasableMonthlyProductCountDBs = new List<PurchaseCountDB>(),
                    MonthlyProductParcel = new List<ParcelInfo>(),
                    MonthlyProductMail = new List<ParcelInfo>(),
                    BiweeklyProductParcel = new List<ParcelInfo>(),
                    BiweeklyProductMail = new List<ParcelInfo>(),
                    WeeklyProductMail = new List<ParcelInfo>(),
                    MissionProgressDBs = new List<MissionProgressDB>()
                };
            }
        }
    }
}
