using GameGateway.Interfaces;
using System.Text;
using System.Text.Json;

namespace GameGateway.Services;

/// <summary>
/// Registry and pipeline for encoding/decoding request data
/// </summary>
public class CodecRegistry
{
    private readonly IEnumerable<ICryptoAdapter> _cryptoAdapters;
    private readonly IEnumerable<ICompressionAdapter> _compressionAdapters;
    private readonly ILogger<CodecRegistry> _logger;

    public CodecRegistry(
        IEnumerable<ICryptoAdapter> cryptoAdapters,
        IEnumerable<ICompressionAdapter> compressionAdapters,
        ILogger<CodecRegistry> logger)
    {
        _cryptoAdapters = cryptoAdapters;
        _compressionAdapters = compressionAdapters;
        _logger = logger;
    }

    /// <summary>
    /// Decodes incoming request data through the codec pipeline
    /// </summary>
    /// <param name="data">Raw mx.dat bytes</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>Decoded JSON string</returns>
    public async Task<string> DecodeAsync(byte[] data, CancellationToken cancellationToken = default)
    {
        var requestId = "decode";
        var (json, _) = await DecodeAsync(data, requestId);
        return json;
    }

    /// <summary>
    /// Decodes incoming request data through the codec pipeline
    /// </summary>
    /// <param name="data">Raw mx.dat bytes</param>
    /// <param name="requestId">Request correlation ID</param>
    /// <returns>Decoded JSON string and codec information</returns>
    public async Task<(string json, string codecSelected)> DecodeAsync(byte[] data, string requestId)
    {
        var codecInfo = new List<string>();
        var currentData = data;

        _logger.LogDebug("Starting decode pipeline for request {RequestId} with {DataLength} bytes", 
            requestId, data.Length);

        try
        {
            // Step 1: Attempt decryption if any crypto adapters can handle the data
            var cryptoAdapter = _cryptoAdapters.FirstOrDefault(a => a.IsEnabled && a.CanDecrypt(currentData));
            if (cryptoAdapter != null)
            {
                _logger.LogDebug("Decrypting with {CryptoAdapter} for request {RequestId}", 
                    cryptoAdapter.Name, requestId);
                currentData = await cryptoAdapter.DecryptAsync(currentData);
                codecInfo.Add($"decrypt:{cryptoAdapter.Name}");
            }
            else
            {
                codecInfo.Add("decrypt:none");
            }

            // Step 2: Attempt decompression if any compression adapters can handle the data
            var compressionAdapter = _compressionAdapters.FirstOrDefault(a => a.IsEnabled && a.CanDecompress(currentData));
            if (compressionAdapter != null)
            {
                _logger.LogDebug("Decompressing with {CompressionAdapter} for request {RequestId}", 
                    compressionAdapter.Name, requestId);
                currentData = await compressionAdapter.DecompressAsync(currentData);
                codecInfo.Add($"decompress:{compressionAdapter.Name}");
            }
            else
            {
                codecInfo.Add("decompress:none");
            }

            // Step 3: Convert to JSON string
            var jsonString = Encoding.UTF8.GetString(currentData);
            
            // Validate JSON format
            try
            {
                JsonDocument.Parse(jsonString);
            }
            catch (JsonException ex)
            {
                _logger.LogError(ex, "Failed to parse decoded JSON for request {RequestId}", requestId);
                throw new InvalidOperationException("Decoded data is not valid JSON", ex);
            }

            var codecSelected = string.Join("+", codecInfo);
            _logger.LogInformation("Successfully decoded request {RequestId} using codec: {CodecSelected}", 
                requestId, codecSelected);

            return (jsonString, codecSelected);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to decode request {RequestId} through pipeline", requestId);
            throw;
        }
    }

    /// <summary>
    /// Encodes response data through the codec pipeline
    /// </summary>
    /// <param name="json">JSON string to encode</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>Encoded bytes</returns>
    public async Task<byte[]> EncodeAsync(string json, CancellationToken cancellationToken = default)
    {
        var requestId = "encode";
        return await EncodeAsync(json, requestId);
    }

    /// <summary>
    /// Encodes response data through the codec pipeline
    /// </summary>
    /// <param name="json">JSON string to encode</param>
    /// <param name="requestId">Request correlation ID</param>
    /// <returns>Encoded bytes</returns>
    public async Task<byte[]> EncodeAsync(string json, string requestId)
    {
        var codecInfo = new List<string>();
        var currentData = Encoding.UTF8.GetBytes(json);

        _logger.LogDebug("Starting encode pipeline for request {RequestId} with {JsonLength} chars", 
            requestId, json.Length);

        try
        {
            // Step 1: Apply compression if enabled
            var compressionAdapter = _compressionAdapters.FirstOrDefault(a => a.IsEnabled);
            if (compressionAdapter != null)
            {
                _logger.LogDebug("Compressing with {CompressionAdapter} for request {RequestId}", 
                    compressionAdapter.Name, requestId);
                currentData = await compressionAdapter.CompressAsync(currentData);
                codecInfo.Add($"compress:{compressionAdapter.Name}");
            }
            else
            {
                codecInfo.Add("compress:none");
            }

            // Step 2: Apply encryption if enabled
            var cryptoAdapter = _cryptoAdapters.FirstOrDefault(a => a.IsEnabled);
            if (cryptoAdapter != null)
            {
                _logger.LogDebug("Encrypting with {CryptoAdapter} for request {RequestId}", 
                    cryptoAdapter.Name, requestId);
                currentData = await cryptoAdapter.EncryptAsync(currentData);
                codecInfo.Add($"encrypt:{cryptoAdapter.Name}");
            }
            else
            {
                codecInfo.Add("encrypt:none");
            }

            var codecSelected = string.Join("+", codecInfo);
            _logger.LogInformation("Successfully encoded response {RequestId} using codec: {CodecSelected}, output {DataLength} bytes", 
                requestId, codecSelected, currentData.Length);

            return currentData;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to encode response {RequestId} through pipeline", requestId);
            throw;
        }
    }

    /// <summary>
    /// Attempts to detect if the data is plain UTF-8 JSON (passthrough case)
    /// </summary>
    /// <param name="data">Data to check</param>
    /// <returns>True if data appears to be plain JSON</returns>
    public bool IsPlainJson(byte[] data)
    {
        try
        {
            if (data.Length == 0) return false;
            
            var text = Encoding.UTF8.GetString(data);
            
            // Quick heuristic: starts with { or [
            if (!text.TrimStart().StartsWith('{') && !text.TrimStart().StartsWith('['))
                return false;
                
            // Attempt to parse as JSON
            JsonDocument.Parse(text);
            return true;
        }
        catch
        {
            return false;
        }
    }
}