using GameGateway.Interfaces;
using NSec.Cryptography;

namespace GameGateway.Crypto;

/// <summary>
/// ChaCha20-Poly1305 cryptographic adapter using NSec
/// </summary>
public class ChaCha20Poly1305Adapter : ICryptoAdapter
{
    private readonly Key? _key;
    private readonly bool _isEnabled;
    private readonly ILogger<ChaCha20Poly1305Adapter> _logger;
    private static readonly AeadAlgorithm Algorithm = AeadAlgorithm.ChaCha20Poly1305;

    // Magic header to identify ChaCha20-Poly1305 encrypted data
    private static readonly byte[] MagicHeader = { 0x43, 0x48, 0x50, 0x31 }; // "CHP1"

    public string Name => "ChaCha20Poly1305";
    public bool IsEnabled => _isEnabled;

    public ChaCha20Poly1305Adapter(IConfiguration configuration, ILogger<ChaCha20Poly1305Adapter> logger)
    {
        _logger = logger;
        
        var encryptionConfig = configuration.GetSection("GameGateway:Codec:Encryption");
        _isEnabled = encryptionConfig.GetValue<bool>("Enabled") && 
                    encryptionConfig.GetValue<string>("Algorithm") == "ChaCha20Poly1305";

        if (_isEnabled)
        {
            var keyString = encryptionConfig.GetValue<string>("Key");
            
            if (!string.IsNullOrEmpty(keyString))
            {
                try
                {
                    var keyBytes = Convert.FromBase64String(keyString);
                    if (keyBytes.Length != Algorithm.KeySize)
                    {
                        _logger.LogError("ChaCha20-Poly1305 key must be exactly {KeySize} bytes", Algorithm.KeySize);
                        _isEnabled = false;
                    }
                    else
                    {
                        _key = Key.Import(Algorithm, keyBytes, KeyBlobFormat.RawSymmetricKey);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Failed to parse ChaCha20-Poly1305 key from Base64");
                    _isEnabled = false;
                }
            }
            else
            {
                // Generate a random key if none provided
                _logger.LogWarning("ChaCha20-Poly1305 enabled but no key provided, generating random key");
                _key = Key.Create(Algorithm, new KeyCreationParameters { ExportPolicy = KeyExportPolicies.AllowPlaintextExport });
            }
        }
        
        _logger.LogInformation("ChaCha20-Poly1305 adapter initialized: Enabled={IsEnabled}", _isEnabled);
    }

    public async Task<byte[]> EncryptAsync(byte[] plaintext)
    {
        if (!_isEnabled || _key == null)
            throw new InvalidOperationException("ChaCha20-Poly1305 adapter is not properly configured");

        try
        {
            // Generate a random nonce for each encryption
            var nonce = new byte[Algorithm.NonceSize];
            using (var rng = System.Security.Cryptography.RandomNumberGenerator.Create())
            {
                rng.GetBytes(nonce);
            }
            
            // Encrypt the data
            var ciphertext = Algorithm.Encrypt(_key, nonce, null, plaintext);
            
            // Create output: MagicHeader + Nonce + Ciphertext (includes auth tag)
            var output = new byte[MagicHeader.Length + nonce.Length + ciphertext.Length];
            var offset = 0;
            
            MagicHeader.CopyTo(output, offset);
            offset += MagicHeader.Length;
            
            nonce.CopyTo(output, offset);
            offset += nonce.Length;
            
            ciphertext.CopyTo(output, offset);
            
            _logger.LogDebug("ChaCha20-Poly1305 encryption completed: {PlaintextLength} -> {CiphertextLength} bytes",
                plaintext.Length, output.Length);
                
            return output;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "ChaCha20-Poly1305 encryption failed");
            throw;
        }
    }

    public async Task<byte[]> DecryptAsync(byte[] ciphertext)
    {
        if (!_isEnabled || _key == null)
            throw new InvalidOperationException("ChaCha20-Poly1305 adapter is not properly configured");

        try
        {
            var minLength = MagicHeader.Length + Algorithm.NonceSize + Algorithm.TagSize;
            if (ciphertext.Length < minLength)
                throw new ArgumentException($"Ciphertext too short for ChaCha20-Poly1305 format (minimum {minLength} bytes)");

            var offset = 0;
            
            // Verify magic header
            if (!ciphertext.AsSpan(offset, MagicHeader.Length).SequenceEqual(MagicHeader))
                throw new ArgumentException("Invalid ChaCha20-Poly1305 magic header");
            offset += MagicHeader.Length;
            
            // Extract nonce
            var nonce = ciphertext.AsSpan(offset, Algorithm.NonceSize).ToArray();
            offset += Algorithm.NonceSize;
            
            // Extract encrypted data (includes auth tag)
            var encryptedData = ciphertext.AsSpan(offset).ToArray();
            
            // Decrypt the data
            var plaintext = Algorithm.Decrypt(_key, nonce, null, encryptedData);
            
            _logger.LogDebug("ChaCha20-Poly1305 decryption completed: {CiphertextLength} -> {PlaintextLength} bytes",
                ciphertext.Length, plaintext.Length);
                
            return plaintext;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "ChaCha20-Poly1305 decryption failed");
            throw;
        }
    }

    public bool CanDecrypt(byte[] data)
    {
        if (!_isEnabled || data.Length < MagicHeader.Length)
            return false;
            
        return data.AsSpan(0, MagicHeader.Length).SequenceEqual(MagicHeader);
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