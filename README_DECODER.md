# Blue Archive MX.DAT Decoder Project

## Overview

This project contains the results of reverse engineering Blue Archive's mx.dat encryption mechanism through analysis of GameAssembly.dll using IDA Pro.

## Key Discoveries

### Encryption Pipeline

1. **JSON Request** → Serialized to UTF-8 bytes
2. **Compression** → Deflate/Zlib compression
3. **Encryption** → ChaCha20-Poly1305 AEAD
4. **Transport** → HTTP POST multipart/form-data

### Cryptographic Details

- **Algorithm**: ChaCha20-Poly1305 (Authenticated Encryption with Associated Data)
- **Key Size**: 256-bit (32 bytes)
- **Nonce Size**: 96-bit (12 bytes)
- **Auth Tag Size**: 128-bit (16 bytes)
- **Key Exchange**: ECDH (Elliptic Curve Diffie-Hellman)
- **Key Derivation**: HKDF-SHA256

### MX.DAT Structure (263 bytes example)

```
Offset  Size  Description
0x00    12    Nonce (random per message)
0x0C    235   Ciphertext (encrypted compressed JSON)
0xF7    16    Authentication tag
```

## Files in This Project

- `report.md` - Detailed reverse engineering report
- `mx_decoder.py` - Python decoder/analyzer tool
- `test_mx.dat` - Test data placeholder

## Using the Decoder

### Analyze MX.DAT Structure

```bash
python mx_decoder.py test_mx.dat --analyze
```

### Decrypt with Known Key

```bash
python mx_decoder.py test_mx.dat --key <32-byte-hex-key>
```

### Derive Key from ECDH Shared Secret

```bash
python mx_decoder.py test_mx.dat --shared-secret <hex-shared-secret>
```

## Current Limitations

1. **No Static Keys**: The game uses dynamic ECDH key exchange - no hardcoded keys found
2. **Session-Based**: Each session has unique keys derived via HKDF
3. **Server Interaction Required**: Keys are negotiated with server during connection

## Next Steps for Full Decryption

To create a working decoder for live traffic, you would need to:

1. **Intercept ECDH Key Exchange**
   - Hook game's ECDH functions during runtime
   - Capture public/private key pairs
   - Or MITM the TLS connection

2. **Extract Session Keys**
   - Hook ChaCha20Poly1305.Init() at 0x189c8eaa0
   - Log the 32-byte key parameter
   - Match keys to specific sessions

3. **Runtime Analysis Options**
   - Use Frida to hook crypto functions
   - Modify game client to log keys
   - Use a debugging proxy with TLS interception

## Technical References

### Key Functions in GameAssembly.dll

- `ChaCha20Poly1305.Init()` - 0x189c8eaa0
- `ChaCha20Poly1305.ProcessBytes()` - 0x189c8eab8
- `ChaCha20Poly1305.DoFinal()` - 0x189c8ea80
- `ECDHBasicAgreement.CalculateAgreement()` - 0x189c960c0
- `HkdfBytesGenerator.GenerateBytes()` - 0x189ca2c00

### Important Strings Located

- "ChaCha20-Poly1305" at 0x18a86f519
- "expand 32-byte k" at 0x18a8f77d4 (ChaCha20 constant)
- "Shared key can't be 1" at 0x18a8b6efa
- "ChaCha20Poly1305 cannot be reused" at 0x189ce7e98

## Security Notes

This analysis is for educational and interoperability purposes. The encryption implementation in Blue Archive follows industry best practices:

- Uses modern AEAD cipher (ChaCha20-Poly1305)
- Implements proper key exchange (ECDH)
- Uses key derivation (HKDF)
- No hardcoded keys or obvious vulnerabilities found

## Contact

For questions about this analysis, please refer to the detailed report.md file.