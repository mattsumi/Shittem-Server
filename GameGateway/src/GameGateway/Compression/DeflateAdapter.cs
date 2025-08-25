using GameGateway.Interfaces;
using System.IO.Compression;

namespace GameGateway.Compression;

/// <summary>
/// Deflate/zlib compression adapter
/// </summary>
public class DeflateAdapter : ICompressionAdapter
{
    private readonly bool _isEnabled;
    private readonly ILogger<DeflateAdapter> _logger;

    // Magic header to identify deflate compressed data
    private static readonly byte[] MagicHeader = { 0x78, 0x9C }; // zlib header for default compression

    public string Name => "Deflate";
    public bool IsEnabled => _isEnabled;

    public DeflateAdapter(IConfiguration configuration, ILogger<DeflateAdapter> logger)
    {
        _logger = logger;
        
        var compressionConfig = configuration.GetSection("GameGateway:Codec:Compression");
        _isEnabled = compressionConfig.GetValue<bool>("Enabled") && 
                    compressionConfig.GetValue<string>("Type") == "Deflate";
        
        _logger.LogInformation("Deflate adapter initialized: Enabled={IsEnabled}", _isEnabled);
    }

    public async Task<byte[]> CompressAsync(byte[] data)
    {
        if (!_isEnabled)
            return data;

        try
        {
            using var outputStream = new MemoryStream();
            using var deflateStream = new DeflateStream(outputStream, CompressionMode.Compress, true);
            
            await deflateStream.WriteAsync(data, 0, data.Length);
            deflateStream.Close();
            
            var compressedData = outputStream.ToArray();
            
            // Add zlib header for better compatibility
            var result = new byte[2 + compressedData.Length + 4]; // header + data + adler32
            
            // zlib header (RFC 1950)
            result[0] = 0x78; // CMF: deflate method, 32k window
            result[1] = 0x9C; // FLG: default compression level, no preset dict
            
            // Copy compressed data
            compressedData.CopyTo(result, 2);
            
            // Calculate and append Adler-32 checksum
            var adler32 = CalculateAdler32(data);
            result[^4] = (byte)((adler32 >> 24) & 0xFF);
            result[^3] = (byte)((adler32 >> 16) & 0xFF);
            result[^2] = (byte)((adler32 >> 8) & 0xFF);
            result[^1] = (byte)(adler32 & 0xFF);
            
            _logger.LogDebug("Deflate compression completed: {OriginalSize} -> {CompressedSize} bytes (ratio: {Ratio:P})",
                data.Length, result.Length, (double)result.Length / data.Length);
                
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Deflate compression failed");
            throw;
        }
    }

    public async Task<byte[]> DecompressAsync(byte[] compressedData)
    {
        if (!_isEnabled)
            return compressedData;

        try
        {
            if (compressedData.Length < 6) // min: 2 byte header + data + 4 byte checksum
                throw new ArgumentException("Compressed data too short for zlib format");

            // Verify zlib header
            if (compressedData[0] != 0x78)
                throw new ArgumentException("Invalid zlib header");

            // Extract deflate data (skip header and checksum)
            var deflateData = new byte[compressedData.Length - 6];
            Array.Copy(compressedData, 2, deflateData, 0, deflateData.Length);
            
            using var inputStream = new MemoryStream(deflateData);
            using var deflateStream = new DeflateStream(inputStream, CompressionMode.Decompress);
            using var outputStream = new MemoryStream();
            
            await deflateStream.CopyToAsync(outputStream);
            
            var decompressedData = outputStream.ToArray();
            
            // Verify Adler-32 checksum
            var expectedAdler32 = (uint)((compressedData[^4] << 24) | 
                                        (compressedData[^3] << 16) | 
                                        (compressedData[^2] << 8) | 
                                         compressedData[^1]);
            var actualAdler32 = CalculateAdler32(decompressedData);
            
            if (expectedAdler32 != actualAdler32)
            {
                throw new InvalidDataException($"Adler-32 checksum mismatch: expected {expectedAdler32:X8}, got {actualAdler32:X8}");
            }
            
            _logger.LogDebug("Deflate decompression completed: {CompressedSize} -> {DecompressedSize} bytes",
                compressedData.Length, decompressedData.Length);
                
            return decompressedData;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Deflate decompression failed");
            throw;
        }
    }

    public bool CanDecompress(byte[] data)
    {
        if (!_isEnabled || data.Length < 2)
            return false;
            
        // Check for zlib header patterns
        return (data[0] == 0x78 && (data[1] == 0x01 || data[1] == 0x9C || data[1] == 0xDA));
    }

    /// <summary>
    /// Calculates Adler-32 checksum as per RFC 1950
    /// </summary>
    private static uint CalculateAdler32(byte[] data)
    {
        const uint BASE = 65521;
        uint a = 1, b = 0;
        
        foreach (byte dataByte in data)
        {
            a = (a + dataByte) % BASE;
            b = (b + a) % BASE;
        }
        
        return (b << 16) | a;
    }
}