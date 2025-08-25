namespace GameGateway.Interfaces;

/// <summary>
/// Interface for cryptographic operations on request/response data
/// </summary>
public interface ICryptoAdapter
{
    /// <summary>
    /// Gets the name of the crypto adapter
    /// </summary>
    string Name { get; }
    
    /// <summary>
    /// Gets whether the adapter is enabled
    /// </summary>
    bool IsEnabled { get; }
    
    /// <summary>
    /// Encrypts the input data
    /// </summary>
    /// <param name="plaintext">The data to encrypt</param>
    /// <returns>The encrypted data</returns>
    Task<byte[]> EncryptAsync(byte[] plaintext);
    
    /// <summary>
    /// Decrypts the input data
    /// </summary>
    /// <param name="ciphertext">The data to decrypt</param>
    /// <returns>The decrypted data</returns>
    Task<byte[]> DecryptAsync(byte[] ciphertext);
    
    /// <summary>
    /// Determines if the given data appears to be encrypted by this adapter
    /// </summary>
    /// <param name="data">The data to check</param>
    /// <returns>True if the data appears to be encrypted by this adapter</returns>
    bool CanDecrypt(byte[] data);
}