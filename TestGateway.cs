using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;

class TestGateway
{
    private static readonly HttpClient client = new HttpClient();

    static async Task Main(string[] args)
    {
        try
        {
            // Test data with proper multipart boundary
            var boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW";
            var content = new StringBuilder();
            content.AppendLine($"--{boundary}");
            content.AppendLine("Content-Disposition: form-data; name=\"mx.dat\"");
            content.AppendLine();
            content.AppendLine("{\"protocol\":\"Account_CheckNexon\",\"data\":{\"SessionKey\":{\"MxToken\":\"test_token_123\",\"AccountServerId\":12345},\"AccountId\":12345}}");
            content.AppendLine($"--{boundary}--");

            var requestContent = new StringContent(content.ToString(), Encoding.UTF8);
            requestContent.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("multipart/form-data");
            requestContent.Headers.ContentType.Parameters.Add(new System.Net.Http.Headers.NameValueHeaderValue("boundary", boundary));

            Console.WriteLine("Sending request to Gateway endpoint...");
            var response = await client.PostAsync("http://localhost:7000/api/gateway", requestContent);
            
            Console.WriteLine($"Status: {response.StatusCode}");
            Console.WriteLine($"Content-Type: {response.Content.Headers.ContentType}");
            
            var responseBytes = await response.Content.ReadAsByteArrayAsync();
            var responseString = Encoding.UTF8.GetString(responseBytes);
            Console.WriteLine($"Response: {responseString}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error: {ex.Message}");
        }
    }
}