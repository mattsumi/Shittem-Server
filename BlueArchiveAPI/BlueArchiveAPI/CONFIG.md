# GameGateway Configuration Guide

This document explains all configuration options available for the Blue Archive API Gateway codec system.

## Configuration Structure

The GameGateway configuration is located under the `GameGateway` section in `appsettings.json` or `appsettings.Development.json`.

## Codec Configuration

### Compression Settings (`GameGateway:Codec:Compression`)

Controls compression applied **only to the `packet` field** in server responses.

- **`Enabled`** (boolean): Enable or disable compression entirely
  - `true`: Apply compression to packet data
  - `false`: No compression (passthrough)
  - Default: `false`

- **`Type`** (string): Compression algorithm to use
  - `"Deflate"`: zlib/deflate compression with Adler-32 checksum
  - Default: `"Deflate"`

**Example:**
```json
"Compression": {
  "Enabled": true,
  "Type": "Deflate"
}
```

### Encryption Settings (`GameGateway:Codec:Encryption`)

Controls encryption applied **only to the `packet` field** in server responses.

- **`Enabled`** (boolean): Enable or disable encryption entirely
  - `true`: Apply encryption to packet data  
  - `false`: No encryption (passthrough)
  - Default: `false`

- **`Algorithm`** (string): Encryption algorithm to use
  - `"AES256GCM"`: AES-256 in GCM mode (requires Key + Nonce)
  - `"ChaCha20Poly1305"`: ChaCha20-Poly1305 AEAD (requires Key only)
  - Default: `"AES256GCM"`

- **`Key`** (string): Base64-encoded encryption key
  - **AES256GCM**: Must be exactly 32 bytes (256 bits)
  - **ChaCha20Poly1305**: Must be exactly 32 bytes (256 bits)
  - If empty and encryption enabled: Random key will be generated
  - Example AES256GCM: `"dGVzdGtleWZvckFFUzI1NkdDTTEyMzQ1Njc4OTA="`
  - Example ChaCha20Poly1305: `"dGVzdGtleWZvckNoYUNoYTIwUG9seTEzMDU="`

- **`Nonce`** (string): Base64-encoded nonce/IV (**AES256GCM only**)
  - **AES256GCM**: Must be exactly 12 bytes (96 bits)
  - **ChaCha20Poly1305**: Ignored (uses random nonce per encryption)
  - If empty and AES256GCM enabled: Random nonce will be generated
  - Example: `"dGVzdG5vbmNlMTI="`

**Example AES256GCM:**
```json
"Encryption": {
  "Enabled": true,
  "Algorithm": "AES256GCM",
  "Key": "dGVzdGtleWZvckFFUzI1NkdDTTEyMzQ1Njc4OTA=",
  "Nonce": "dGVzdG5vbmNlMTI="
}
```

**Example ChaCha20Poly1305:**
```json
"Encryption": {
  "Enabled": true,
  "Algorithm": "ChaCha20Poly1305",
  "Key": "dGVzdGtleWZvckNoYUNoYTIwUG9seTEzMDU=",
  "Nonce": ""
}
```

## Session Configuration (`GameGateway:Session`)

Controls session management and cookie handling.

- **`CookieName`** (string): Name of the primary session cookie
  - Typically `"uuid"` for Blue Archive
  - Default: `"uuid"`

- **`CookiePath`** (string): Path scope for session cookies
  - Default: `"/"`

**Example:**
```json
"Session": {
  "CookieName": "uuid",
  "CookiePath": "/"
}
```

## Load Balancer Configuration (`GameGateway:LoadBalancer`)

Controls AWS load balancer cookie values for compatibility.

- **`Cookies.LB`** (string): Value for AWSALB cookie
  - Default: `"node1"`

- **`Cookies.LBCORS`** (string): Value for AWSALBCORS cookie  
  - Default: `"cors1"`

**Example:**
```json
"LoadBalancer": {
  "Cookies": {
    "LB": "production-node-1",
    "LBCORS": "production-cors-1"
  }
}
```

## Codec Pipeline Behavior

### Processing Order

**Decoding (Incoming Requests):**
1. Detect and decrypt (if encrypted data detected)
2. Detect and decompress (if compressed data detected)  
3. Parse as JSON

**Encoding (Outgoing Responses):**
1. Serialize response object to JSON
2. Compress packet data (if compression enabled)
3. Encrypt packet data (if encryption enabled)
4. Embed in ServerPacket wrapper as plain JSON

### Packet-Only Processing

**Important**: Only the `packet` field in server responses is processed through the codec pipeline. The outer response structure remains plain JSON:

```json
{
  "protocol": "Account_Auth",
  "packet": "<compressed/encrypted or plain JSON packet data>"
}
```

### Magic Headers

Each adapter uses magic headers to identify its data format:

- **AES256GCM**: `41 47 43 4D` ("AGCM")
- **ChaCha20Poly1305**: `43 48 50 31` ("CHP1") 
- **Deflate**: `78 9C` (zlib header)

## Key Generation Examples

### Generate AES-256 Key (32 bytes)
```bash
# Generate random 32-byte key
openssl rand -base64 32
```

### Generate AES-256 Nonce (12 bytes)  
```bash
# Generate random 12-byte nonce
openssl rand -base64 12
```

### Generate ChaCha20-Poly1305 Key (32 bytes)
```bash
# Generate random 32-byte key
openssl rand -base64 32
```

## Complete Configuration Example

```json
{
  "GameGateway": {
    "Codec": {
      "Compression": {
        "Enabled": true,
        "Type": "Deflate"
      },
      "Encryption": {
        "Enabled": true,
        "Algorithm": "AES256GCM", 
        "Key": "dGVzdGtleWZvckFFUzI1NkdDTTEyMzQ1Njc4OTA=",
        "Nonce": "dGVzdG5vbmNlMTI="
      }
    },
    "Session": {
      "CookieName": "uuid",
      "CookiePath": "/"
    },
    "LoadBalancer": {
      "Cookies": {
        "LB": "prod-node-1", 
        "LBCORS": "prod-cors-1"
      }
    }
  }
}