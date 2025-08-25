using System.Text;

namespace GameGateway.Services;

/// <summary>
/// Parser for multipart/form-data requests to extract mx.dat content
/// </summary>
public class MultipartParser
{
    private readonly ILogger<MultipartParser> _logger;

    public MultipartParser(ILogger<MultipartParser> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Parse multipart/form-data request and extract all form fields
    /// </summary>
    /// <param name="request">HTTP request</param>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <returns>Dictionary of form field names to byte arrays</returns>
    public async Task<Dictionary<string, byte[]>> ParseAsync(HttpRequest request, CancellationToken cancellationToken = default)
    {
        var contentType = request.ContentType;
        if (string.IsNullOrEmpty(contentType) || !contentType.StartsWith("multipart/form-data", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Content-Type must be multipart/form-data", nameof(request));
        }

        var requestId = "unknown"; // We'll get this from the context elsewhere
        var mxData = await ExtractMxDataAsync(contentType, request.Body, requestId);
        
        return new Dictionary<string, byte[]>
        {
            ["mx.dat"] = mxData
        };
    }

    /// <summary>
    /// Extracts the mx.dat part from multipart/form-data request
    /// </summary>
    /// <param name="contentType">Content-Type header value</param>
    /// <param name="body">Request body stream</param>
    /// <param name="requestId">Request correlation ID</param>
    /// <returns>The mx.dat content bytes</returns>
    public async Task<byte[]> ExtractMxDataAsync(string contentType, Stream body, string requestId)
    {
        if (string.IsNullOrEmpty(contentType) || !contentType.StartsWith("multipart/form-data", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Content-Type must be multipart/form-data", nameof(contentType));
        }

        // Extract boundary from Content-Type header
        var boundary = ExtractBoundary(contentType);
        if (string.IsNullOrEmpty(boundary))
        {
            throw new ArgumentException("No boundary found in Content-Type header", nameof(contentType));
        }

        _logger.LogInformation("Parsing multipart request {RequestId} with boundary: {Boundary}", requestId, boundary);

        try
        {
            using var reader = new StreamReader(body, Encoding.UTF8, leaveOpen: true);
            var content = await reader.ReadToEndAsync();
            
            return ParseMultipartContent(content, boundary, requestId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse multipart request {RequestId}", requestId);
            throw;
        }
    }

    /// <summary>
    /// Extracts boundary string from Content-Type header
    /// </summary>
    private static string ExtractBoundary(string contentType)
    {
        const string boundaryPrefix = "boundary=";
        var boundaryIndex = contentType.IndexOf(boundaryPrefix, StringComparison.OrdinalIgnoreCase);
        
        if (boundaryIndex == -1)
            return string.Empty;

        var boundaryStart = boundaryIndex + boundaryPrefix.Length;
        var boundaryEnd = contentType.IndexOf(';', boundaryStart);
        
        var boundary = boundaryEnd == -1 
            ? contentType[boundaryStart..] 
            : contentType[boundaryStart..boundaryEnd];
        
        // Remove quotes if present
        boundary = boundary.Trim().Trim('"');
        
        return boundary;
    }

    /// <summary>
    /// Parses multipart content and extracts mx part
    /// </summary>
    private byte[] ParseMultipartContent(string content, string boundary, string requestId)
    {
        var boundaryMarker = "--" + boundary;
        var endBoundaryMarker = boundaryMarker + "--";
        
        _logger.LogInformation("Parsing content with boundary marker: '{BoundaryMarker}' for request {RequestId}", boundaryMarker, requestId);
        _logger.LogInformation("Raw content preview (first 500 chars): '{Content}' for request {RequestId}",
            content.Length > 500 ? content[..500] : content, requestId);
        
        var parts = content.Split(new[] { boundaryMarker }, StringSplitOptions.RemoveEmptyEntries);
        
        _logger.LogInformation("Found {PartCount} parts in multipart request {RequestId}", parts.Length, requestId);

        for (int partIndex = 0; partIndex < parts.Length; partIndex++)
        {
            var part = parts[partIndex];
            _logger.LogInformation("Raw part {PartIndex}: '{PartContent}' for request {RequestId}",
                partIndex, part.Length > 200 ? part[..200] + "..." : part, requestId);
            
            if (string.IsNullOrWhiteSpace(part) || part.Trim().StartsWith("--") || part.Trim().Length == 0)
            {
                _logger.LogInformation("Skipping empty/boundary part {PartIndex} for request {RequestId}", partIndex, requestId);
                continue;
            }

            var lines = part.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);
            var headerEndIndex = -1;
            var mxPartFound = false;
            var filename = string.Empty;
            var contentType = string.Empty;

            _logger.LogInformation("Processing part {PartIndex} with {LineCount} lines in request {RequestId}", partIndex, lines.Length, requestId);

            // Parse headers - skip initial empty lines
            int startIndex = 0;
            while (startIndex < lines.Length && string.IsNullOrWhiteSpace(lines[startIndex]))
            {
                startIndex++;
            }
            
            // Parse headers
            for (int i = startIndex; i < lines.Length; i++)
            {
                var line = lines[i].Trim();
                _logger.LogInformation("Part {PartIndex} Line {LineIndex}: '{Line}' in request {RequestId}", partIndex, i, line, requestId);
                
                if (string.IsNullOrEmpty(line))
                {
                    headerEndIndex = i;
                    break;
                }

                if (line.StartsWith("Content-Disposition:", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogInformation("Found Content-Disposition: '{Line}' in request {RequestId}", line, requestId);
                    if (line.Contains("name=\"mx\"", StringComparison.OrdinalIgnoreCase) ||
                        line.Contains("name=\"mx.dat\"", StringComparison.OrdinalIgnoreCase))
                    {
                        mxPartFound = true;
                        _logger.LogInformation("Found mx part in request {RequestId}", requestId);
                    }
                    
                    // Extract filename
                    var filenameMatch = System.Text.RegularExpressions.Regex.Match(line, @"filename[*]?=[""']?([^""';\s]+)[""']?", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                    if (filenameMatch.Success)
                    {
                        filename = filenameMatch.Groups[1].Value;
                    }
                }
                else if (line.StartsWith("Content-Type:", StringComparison.OrdinalIgnoreCase))
                {
                    contentType = line["Content-Type:".Length..].Trim();
                }
            }

            if (!mxPartFound)
            {
                _logger.LogDebug("Part is not mx part in request {RequestId}", requestId);
                continue;
            }

            if (filename != "mx.dat")
            {
                _logger.LogWarning("mx part has incorrect filename '{Filename}' in request {RequestId}", filename, requestId);
            }

            if (contentType != "application/octet-stream")
            {
                _logger.LogWarning("mx part has incorrect content type '{ContentType}' in request {RequestId}", contentType, requestId);
            }

            // Extract body content after headers
            if (headerEndIndex == -1 || headerEndIndex + 1 >= lines.Length)
            {
                throw new InvalidOperationException($"No content found in mx part for request {requestId}");
            }

            var bodyLines = lines.Skip(headerEndIndex + 1).ToArray();
            var bodyContent = string.Join("\n", bodyLines);
            
            // Remove trailing boundary markers
            if (bodyContent.EndsWith(endBoundaryMarker))
            {
                bodyContent = bodyContent[..^endBoundaryMarker.Length];
            }
            else if (bodyContent.EndsWith(boundaryMarker))
            {
                bodyContent = bodyContent[..^boundaryMarker.Length];
            }
            
            // Convert to bytes - assuming the data was base64 encoded in form or is binary
            try
            {
                // Try to decode as base64 first
                var bytes = Convert.FromBase64String(bodyContent.Trim());
                _logger.LogInformation("Successfully extracted mx.dat as base64: {ByteCount} bytes for request {RequestId}", 
                    bytes.Length, requestId);
                return bytes;
            }
            catch (FormatException)
            {
                // If not base64, treat as raw bytes
                var bytes = Encoding.UTF8.GetBytes(bodyContent);
                _logger.LogInformation("Successfully extracted mx.dat as raw bytes: {ByteCount} bytes for request {RequestId}", 
                    bytes.Length, requestId);
                return bytes;
            }
        }

        throw new InvalidOperationException($"No mx part found in multipart request {requestId}");
    }
}