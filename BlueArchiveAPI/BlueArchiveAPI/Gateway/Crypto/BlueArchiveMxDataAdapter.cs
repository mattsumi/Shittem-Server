using BlueArchiveAPI.Gateway.Interfaces;
using NSec.Cryptography;
using System.Security.Cryptography;

namespace BlueArchiveAPI.Gateway.Crypto;

/// <summary>
/// Blue Archive-specific mx.dat cryptographic adapter using ChaCha20-Poly1305
/// Implements the exact format expected by Blue Archive client:
/// [12 bytes nonce][ciphertext with 16-byte auth tag]
/// </summary>
public class BlueArchiveMxDataAdapter : ICryptoAdapter
{
    private readonly Key? _key;
    private readonly bool _isEnabled;
    private readonly ILogger<BlueArchiveMxDataAdapter> _logger;
    private static readonly AeadAlgorithm Algorithm = AeadAlgorithm.ChaCha20Poly1305;
    
    // Blue Archive mx.dat format: no magic header, just nonce + ciphertext+tag
    private const int NonceSize = 12; // ChaCha20 nonce size
    private const int TagSize = 16;   // Poly1305 tag size

    public string Name => "BlueArchiveMxData";
    public bool IsEnabled => _isEnabled;

    public BlueArchiveMxDataAdapter(IConfiguration configuration, ILogger<BlueArchiveMxDataAdapter> logger)
    {
        _logger = logger;
        
        var mxDataConfig = configuration.GetSection("GameGateway:MxData");
        _isEnabled = mxDataConfig.GetValue<bool>("Enabled", true);

        if (_isEnabled)
        {
            var keyString = mxDataConfig.GetValue<string>("Key");
            
            if (!string.IsNullOrEmpty(keyString))
            {
                try
                {
                    var keyBytes = Convert.FromBase64String(keyString);
                    if (keyBytes.Length != Algorithm.KeySize)
                    {
                        _logger.LogError("Blue Archive mx.dat key must be exactly {KeySize} bytes", Algorithm.KeySize);
                        _isEnabled = false;
                    }
                    else
                    {
                        _key = Key.Import(Algorithm, keyBytes, KeyBlobFormat.RawSymmetricKey);
                        _logger.LogInformation("Blue Archive mx.dat adapter initialized with provided key");
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Failed to parse Blue Archive mx.dat key from Base64");
                    _isEnabled = false;
                }
            }
            else
            {
                // Generate a session key (in real implementation, this would come from ECDH + HKDF)
                _logger.LogWarning("Blue Archive mx.dat enabled but no key provided, generating random session key");
                _key = Key.Create(Algorithm, new KeyCreationParameters { ExportPolicy = KeyExportPolicies.AllowPlaintextExport });
                
                // Log the generated key for debugging (remove in production)
                var keyBytes = _key.Export(KeyBlobFormat.RawSymmetricKey);
                _logger.LogInformation("Generated Blue Archive mx.dat key (Base64): {Key}", Convert.ToBase64String(keyBytes));
            }
        }
        
        _logger.LogInformation("Blue Archive mx.dat adapter initialized: Enabled={IsEnabled}", _isEnabled);
    }

    public Task<byte[]> EncryptAsync(byte[] plaintext)
    {
        if (!_isEnabled || _key == null)
            throw new InvalidOperationException("Blue Archive mx.dat adapter is not properly configured");

        try
        {
            // Generate a random nonce for each encryption (12 bytes for ChaCha20)
            var nonce = new byte[NonceSize];
            using (var rng = RandomNumberGenerator.Create())
            {
                rng.GetBytes(nonce);
            }
            
            // Encrypt the data using ChaCha20-Poly1305
            var ciphertext = Algorithm.Encrypt(_key, nonce, null, plaintext);
            
            // Blue Archive format: [nonce][ciphertext+tag]
            var output = new byte[NonceSize + ciphertext.Length];
            nonce.CopyTo(output, 0);
            ciphertext.CopyTo(output, NonceSize);
            
            _logger.LogDebug("Blue Archive mx.dat encryption completed: {PlaintextLength} -> {OutputLength} bytes (nonce: {NonceSize}, ciphertext+tag: {CiphertextLength})",
                plaintext.Length, output.Length, NonceSize, ciphertext.Length);
                
            return Task.FromResult(output);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Blue Archive mx.dat encryption failed");
            throw;
        }
    }

    public Task<byte[]> DecryptAsync(byte[] ciphertext)
    {
        if (!_isEnabled || _key == null)
            throw new InvalidOperationException("Blue Archive mx.dat adapter is not properly configured");

        try
        {
            var minLength = NonceSize + TagSize;
            if (ciphertext.Length < minLength)
                throw new ArgumentException($"mx.dat too short for Blue Archive format (minimum {minLength} bytes, got {ciphertext.Length})");

            // Extract nonce (first 12 bytes)
            var nonce = ciphertext.AsSpan(0, NonceSize).ToArray();
            
            // Extract encrypted data with auth tag (remaining bytes)
            var encryptedData = ciphertext.AsSpan(NonceSize).ToArray();
            
            _logger.LogDebug("Blue Archive mx.dat structure: total={TotalLength}, nonce={NonceLength}, ciphertext+tag={EncryptedLength}",
                ciphertext.Length, nonce.Length, encryptedData.Length);
            
            // Decrypt the data
            var plaintext = Algorithm.Decrypt(_key!, nonce, null, encryptedData);
            
            _logger.LogDebug("Blue Archive mx.dat decryption completed: {CiphertextLength} -> {PlaintextLength} bytes",
                ciphertext.Length, plaintext.Length);
                
            return Task.FromResult(plaintext);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Blue Archive mx.dat decryption failed: {Message}", ex.Message);
            throw;
        }
    }

    public bool CanDecrypt(byte[] data)
    {
        if (!_isEnabled || data.Length < NonceSize + TagSize)
            return false;
            
        // Blue Archive mx.dat has no magic header, but we can check if other adapters can't handle it
        // This is a heuristic - we assume if it's the right size format and doesn't have other magic headers,
        // then it might be Blue Archive mx.dat format
        
        // Check it's not the generic ChaCha20-Poly1305 format (has magic header)
        var chachaHeader = new byte[] { 0x43, 0x48, 0x50, 0x31 }; // "CHP1"
        if (data.Length >= 4 && data.AsSpan(0, 4).SequenceEqual(chachaHeader))
            return false;
            
        // Check it's not the AES256GCM format (has magic header)
        var aesHeader = new byte[] { 0x41, 0x47, 0x43, 0x4D }; // "AGCM"
        if (data.Length >= 4 && data.AsSpan(0, 4).SequenceEqual(aesHeader))
            return false;
            
        // Check it's not zlib compressed data
        if (data.Length >= 2 && data[0] == 0x78 && (data[1] == 0x9C || data[1] == 0x01 || data[1] == 0xDA))
            return false;
            
        // If it doesn't match other formats and has reasonable size, assume it's Blue Archive mx.dat
        return true;
    }

    /// <summary>
    /// Creates a key from ECDH shared secret using HKDF as described in the report
    /// </summary>
    /// <param name="sharedSecret">ECDH shared secret</param>
    /// <param name="salt">16-byte salt for HKDF</param>
    /// <param name="info">Info string for HKDF (default: "mx.dat encryption")</param>
    /// <returns>Derived 32-byte key</returns>
    public static byte[] DeriveKeyFromECDH(byte[] sharedSecret, byte[] salt, string info = "mx.dat encryption")
    {
        // Use HKDF-SHA256 as specified in the report
        var infoBytes = System.Text.Encoding.UTF8.GetBytes(info);
        var key = new byte[32]; // ChaCha20 uses 256-bit keys
        
        HKDF.DeriveKey(HashAlgorithmName.SHA256, sharedSecret, key, salt, infoBytes);
        return key;
    }

    protected virtual void Dispose(bool disposing)
    {
        if (disposing)
        {
            _key?.Dispose();
        }
    }

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }
}