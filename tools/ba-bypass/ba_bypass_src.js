// need help with this
'use strict';

const Il2Cpp = require("frida-il2cpp-bridge");

const LOG_VERBOSE = true;
function log(...a){ console.log("[BA-BYPASS]", ...a); }

function tryHookChaCha() {
  let hooked = 0;

  // Common namespaces seen in Unity IL2CPP builds using BouncyCastle via BestHTTP/BC:
  const classNames = [
    "BestHTTP.SecureProtocol.Org.BouncyCastle.Crypto.Modes.ChaCha20Poly1305",
    "Org.BouncyCastle.Crypto.Modes.ChaCha20Poly1305"
  ];

  for (const name of classNames) {
    const klass = Il2Cpp.classes[name];
    if (!klass) continue;

    const methods = klass.methods;
    for (const m of methods) {
      // We only care about ProcessBytes and DoFinal
      if (m.name.indexOf("ProcessBytes") < 0 && m.name.indexOf("DoFinal") < 0) continue;

      const original = m.implementation;
      if (!original) continue;

      // Replace Encrypt/Decrypt with identity and forge a valid tag.
      m.implementation = function () {
        const n = `${name}.${m.name}`;
        try {
          // Heuristic for ProcessBytes(in, inOff, len, out, outOff)
          if (m.name.indexOf("ProcessBytes") >= 0 && arguments.length >= 5) {
            const inBuf  = arguments[0];
            const inOff  = arguments[1].toInt32 ? arguments[1].toInt32() : arguments[1];
            const len    = arguments[2].toInt32 ? arguments[2].toInt32() : arguments[2];
            const outBuf = arguments[3];
            const outOff = arguments[4].toInt32 ? arguments[4].toInt32() : arguments[4];

            // IL2CPP Byte[] data pointer is at 0x20 from object start (typical, works on current Unity).
            const IN  = inBuf.add(0x20).add(inOff);
            const OUT = outBuf.add(0x20).add(outOff);
            Memory.copy(OUT, IN, len);
            if (LOG_VERBOSE) log("ChaCha ProcessBytes pass-through", len);
            return len; // bytes written
          }

          // Heuristic for DoFinal(out, outOff) -> write 16-byte tag
          if (m.name.indexOf("DoFinal") >= 0) {
            if (arguments.length >= 2) {
              const outBuf = arguments[0];
              const outOff = arguments[1].toInt32 ? arguments[1].toInt32() : arguments[1];
              const OUT = outBuf.add(0x20).add(outOff);
              Memory.set(OUT, 0, 16); // forge 16 zero bytes as tag
              if (LOG_VERBOSE) log("ChaCha DoFinal forged tag (16 zero bytes)");
              return 16;
            }
            if (LOG_VERBOSE) log("ChaCha DoFinal no out buffer; returning 16");
            return 16;
          }
        } catch (e) {
          if (LOG_VERBOSE) log("ChaCha hook path error; falling back to original:", n, e);
          return original.apply(this, arguments);
        }

        return original.apply(this, arguments);
      };

      hooked++;
      log("Hooked:", name, m.name);
    }
  }

  if (!hooked) log("ChaCha20Poly1305 class not found yet. Different namespace? Dumping candidates…");
  return hooked > 0;
}

function tryHookCompression() {
  let hooked = 0;

  // We target both stock System.IO.Compression and Ionic.Zlib used by BestHTTP.
  const candidates = [
    // .NET
    ["System.IO.Compression.DeflateStream", ["Write", "Read"]],
    // Ionic
    ["Ionic.Zlib.ZlibStream", ["Write", "Read"]],
    ["Ionic.Zlib.DeflateStream", ["Write", "Read"]],
  ];

  for (const [klassName, methods] of candidates) {
    const klass = Il2Cpp.classes[klassName];
    if (!klass) continue;

    for (const mn of methods) {
      const ms = klass.methods.filter(m => m.name.indexOf(mn) >= 0);
      for (const m of ms) {
        const original = m.implementation;
        if (!original) continue;

        m.implementation = function () {
          // Identity transform: instead of letting the stream compress/decompress,
          // forward the raw buffer to the underlying stream as-is.
          // Many stream classes expose a get_BaseStream() or have a private field like "_stream".
          try {
            // Try get_BaseStream virtual/property if present
            let baseStream = null;
            const getBase = this.$class.methods.find(mm => mm.name.indexOf("get_BaseStream") >= 0);
            if (getBase) baseStream = getBase.invoke(this);
            if (!baseStream) {
              // Try common private field names
              const fld = this.$class.fields.find(f =>
                ["_stream","stream","_baseStream","baseStream","_outStream"].includes(f.name));
              if (fld) baseStream = fld.value(this);
            }

            if (!baseStream) {
              // If we can't find an underlying stream, just bypass by calling original and returning.
              if (LOG_VERBOSE) log(`${klassName}.${m.name}: no BaseStream found, leaving original.`);
              return original.apply(this, arguments);
            }

            // Expect signature Write(byte[] buffer, int offset, int count) / Read(…)
            const isWrite = m.name.indexOf("Write") >= 0;
            const isRead  = m.name.indexOf("Read")  >= 0;

            if (isWrite && arguments.length >= 3) {
              const buf   = arguments[0];
              const off   = arguments[1].toInt32 ? arguments[1].toInt32() : arguments[1];
              const count = arguments[2].toInt32 ? arguments[2].toInt32() : arguments[2];

              // Call BaseStream.Write(buffer, offset, count) directly
              const writeM = baseStream.$class.methods.find(mm => mm.name === "Write");
              if (writeM) {
                writeM.invoke(baseStream, buf, off, count);
                if (LOG_VERBOSE) log(`${klassName}.Write passthrough ${count} bytes`);
                return; // void
              }
            }

            if (isRead && arguments.length >= 3) {
              // For Read, we’ll just delegate to original (identity here is harmless),
              // because bypassing Read requires mirroring upstream semantics.
              return original.apply(this, arguments);
            }

            return original.apply(this, arguments);
          } catch (e) {
            if (LOG_VERBOSE) log(`${klassName}.${m.name} passthrough error; using original:`, e);
            return original.apply(this, arguments);
          }
        };

        hooked++;
        log("Hooked:", klassName, m.name);
      }
    }
  }

  if (!hooked) log("No compression classes found yet.");
  return hooked > 0;
}

async function waitAndHook() {
  try {
    // Newer frida-il2cpp-bridge exposes initialize() but not perform().
    await Il2Cpp.initialize();
    try {
      log("IL2CPP ready. Unity", Il2Cpp.unityVersion);
    } catch (_) {
      log("IL2CPP ready. (Unity version unavailable)");
    }

    // Try hooking repeatedly for a few seconds in case assemblies are late-loaded.
    let tries = 0;
    const t = setInterval(() => {
      const c1 = tryHookChaCha();
      const c2 = tryHookCompression();
      tries++;

      if ((c1 || tries >= 10) && (c2 || tries >= 10)) {
        clearInterval(t);
        log("Bypass installed (crypto:", !!c1, " compression:", !!c2, "). Login then flip proxy.");
      } else {
        if (LOG_VERBOSE) log("Retrying hooks…", tries);
      }
    }, 1000);
  } catch (e) {
    log("Il2Cpp.initialize() failed:", e);
  }
}

waitAndHook();
