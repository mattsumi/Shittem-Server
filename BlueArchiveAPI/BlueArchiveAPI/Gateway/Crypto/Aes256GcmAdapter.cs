using BlueArchiveAPI.Gateway.Interfaces;
using System.Security.Cryptography;

namespace BlueArchiveAPI.Gateway.Crypto;

/// <summary>
/// AES-256-GCM cryptographic adapter
/// </summary>
public class Aes256GcmAdapter : ICryptoAdapter
{
    private readonly byte[]? _key;
    private readonly byte[]? _nonce;
    private readonly bool _isEnabled;
    private readonly ILogger<Aes256GcmAdapter> _logger;

    // Magic header to identify AES-256-GCM encrypted data
    private static readonly byte[] MagicHeader = { 0x41, 0x47, 0x43, 0x4D }; // "AGCM"

    public string Name => "AES256GCM";
    public bool IsEnabled => _isEnabled;

    public Aes256GcmAdapter(IConfiguration configuration, ILogger<Aes256GcmAdapter> logger)
    {
        _logger = logger;
        
        var encryptionConfig = configuration.GetSection("GameGateway:Codec:Encryption");
        _isEnabled = encryptionConfig.GetValue<bool>("Enabled") && 
                    encryptionConfig.GetValue<string>("Algorithm") == "AES256GCM";

        if (_isEnabled)
        {
            var keyString = encryptionConfig.GetValue<string>("Key");
            var nonceString = encryptionConfig.GetValue<string>("Nonce");
            
            if (!string.IsNullOrEmpty(keyString))
            {
                try
                {
                    _key = Convert.FromBase64String(keyString);
                    if (_key.Length != 32)
                    {
                        _logger.LogError("AES-256-GCM key must be exactly 32 bytes (256 bits)");
                        _isEnabled = false;
                    }
                }
                catch (FormatException ex)
                {
                    _logger.LogError(ex, "Failed to parse AES-256-GCM key from Base64");
                    _isEnabled = false;
                }
            }
            
            if (!string.IsNullOrEmpty(nonceString))
            {
                try
                {
                    _nonce = Convert.FromBase64String(nonceString);
                    if (_nonce.Length != 12)
                    {
                        _logger.LogError("AES-256-GCM nonce must be exactly 12 bytes (96 bits)");
                        _isEnabled = false;
                    }
                }
                catch (FormatException ex)
                {
                    _logger.LogError(ex, "Failed to parse AES-256-GCM nonce from Base64");
                    _isEnabled = false;
                }
            }
            
            if (_key == null)
            {
                _logger.LogWarning("AES-256-GCM enabled but no key provided, generating random key");
                _key = new byte[32];
                using var rng = RandomNumberGenerator.Create();
                rng.GetBytes(_key);
            }
            
            if (_nonce == null)
            {
                _logger.LogWarning("AES-256-GCM enabled but no nonce provided, generating random nonce");
                _nonce = new byte[12];
                using var rng = RandomNumberGenerator.Create();
                rng.GetBytes(_nonce);
            }
        }
        
        _logger.LogInformation("AES-256-GCM adapter initialized: Enabled={IsEnabled}", _isEnabled);
    }

    public async Task<byte[]> EncryptAsync(byte[] plaintext)
    {
        if (!_isEnabled || _key == null || _nonce == null)
            throw new InvalidOperationException("AES-256-GCM adapter is not properly configured");

        try
        {
            using var aes = new AesGcm(_key);
            
            var ciphertext = new byte[plaintext.Length];
            var tag = new byte[16]; // GCM tag is 16 bytes
            
            aes.Encrypt(_nonce, plaintext, ciphertext, tag);
            
            // Create output: MagicHeader + Nonce + Tag + Ciphertext
            var output = new byte[MagicHeader.Length + _nonce.Length + tag.Length + ciphertext.Length];
            var offset = 0;
            
            MagicHeader.CopyTo(output, offset);
            offset += MagicHeader.Length;
            
            _nonce.CopyTo(output, offset);
            offset += _nonce.Length;
            
            tag.CopyTo(output, offset);
            offset += tag.Length;
            
            ciphertext.CopyTo(output, offset);
            
            _logger.LogDebug("AES-256-GCM encryption completed: {PlaintextLength} -> {CiphertextLength} bytes",
                plaintext.Length, output.Length);
                
            return output;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AES-256-GCM encryption failed");
            throw;
        }
    }

    public async Task<byte[]> DecryptAsync(byte[] ciphertext)
    {
        if (!_isEnabled || _key == null)
            throw new InvalidOperationException("AES-256-GCM adapter is not properly configured");

        try
        {
            if (ciphertext.Length < MagicHeader.Length + 12 + 16)
                throw new ArgumentException("Ciphertext too short for AES-256-GCM format");

            var offset = 0;
            
            // Verify magic header
            if (!ciphertext.AsSpan(offset, MagicHeader.Length).SequenceEqual(MagicHeader))
                throw new ArgumentException("Invalid AES-256-GCM magic header");
            offset += MagicHeader.Length;
            
            // Extract nonce
            var nonce = ciphertext.AsSpan(offset, 12).ToArray();
            offset += 12;
            
            // Extract tag
            var tag = ciphertext.AsSpan(offset, 16).ToArray();
            offset += 16;
            
            // Extract actual ciphertext
            var encryptedData = ciphertext.AsSpan(offset).ToArray();
            
            using var aes = new AesGcm(_key);
            var plaintext = new byte[encryptedData.Length];
            
            aes.Decrypt(nonce, encryptedData, tag, plaintext);
            
            _logger.LogDebug("AES-256-GCM decryption completed: {CiphertextLength} -> {PlaintextLength} bytes",
                ciphertext.Length, plaintext.Length);
                
            return plaintext;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AES-256-GCM decryption failed");
            throw;
        }
    }

    public bool CanDecrypt(byte[] data)
    {
        if (!_isEnabled || data.Length < MagicHeader.Length)
            return false;
            
        return data.AsSpan(0, MagicHeader.Length).SequenceEqual(MagicHeader);
    }
}