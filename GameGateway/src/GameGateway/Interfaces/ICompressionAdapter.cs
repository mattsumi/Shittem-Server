namespace GameGateway.Interfaces;

/// <summary>
/// Interface for compression operations on request/response data
/// </summary>
public interface ICompressionAdapter
{
    /// <summary>
    /// Gets the name of the compression adapter
    /// </summary>
    string Name { get; }
    
    /// <summary>
    /// Gets whether the adapter is enabled
    /// </summary>
    bool IsEnabled { get; }
    
    /// <summary>
    /// Compresses the input data
    /// </summary>
    /// <param name="data">The data to compress</param>
    /// <returns>The compressed data</returns>
    Task<byte[]> CompressAsync(byte[] data);
    
    /// <summary>
    /// Decompresses the input data
    /// </summary>
    /// <param name="compressedData">The data to decompress</param>
    /// <returns>The decompressed data</returns>
    Task<byte[]> DecompressAsync(byte[] compressedData);
    
    /// <summary>
    /// Determines if the given data appears to be compressed by this adapter
    /// </summary>
    /// <param name="data">The data to check</param>
    /// <returns>True if the data appears to be compressed by this adapter</returns>
    bool CanDecompress(byte[] data);
}