'use strict';

// Be resilient to different frida-il2cpp-bridge shapes/versions.
const bridge = require("frida-il2cpp-bridge");
const Il2Cpp = bridge.Il2Cpp || bridge.default || bridge;

const LOG_VERBOSE = true;
function log(...a){ console.log("[BA-BYPASS]", ...a); }

function tryHookChaCha() {
  let hooked = 0;

  const classNames = [
    "BestHTTP.SecureProtocol.Org.BouncyCastle.Crypto.Modes.ChaCha20Poly1305",
    "Org.BouncyCastle.Crypto.Modes.ChaCha20Poly1305"
  ];

  for (const name of classNames) {
    const klass = (Il2Cpp && Il2Cpp.classes) ? Il2Cpp.classes[name] : null;
    if (!klass) continue;

    for (const m of klass.methods) {
      if (m.name.indexOf("ProcessBytes") < 0 && m.name.indexOf("DoFinal") < 0) continue;

      const original = m.implementation;
      if (!original) continue;

      m.implementation = function () {
        const n = `${name}.${m.name}`;
        try {
          if (m.name.indexOf("ProcessBytes") >= 0 && arguments.length >= 5) {
            const inBuf  = arguments[0];
            const inOff  = arguments[1].toInt32 ? arguments[1].toInt32() : arguments[1];
            const len    = arguments[2].toInt32 ? arguments[2].toInt32() : arguments[2];
            const outBuf = arguments[3];
            const outOff = arguments[4].toInt32 ? arguments[4].toInt32() : arguments[4];

            const IN  = inBuf.add(0x20).add(inOff);
            const OUT = outBuf.add(0x20).add(outOff);
            Memory.copy(OUT, IN, len);
            if (LOG_VERBOSE) log("ChaCha ProcessBytes pass-through", len);
            return len;
          }

          if (m.name.indexOf("DoFinal") >= 0) {
            if (arguments.length >= 2) {
              const outBuf = arguments[0];
              const outOff = arguments[1].toInt32 ? arguments[1].toInt32() : arguments[1];
              const OUT = outBuf.add(0x20).add(outOff);
              Memory.set(OUT, 0, 16); // zero tag
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

  if (!hooked) log("ChaCha20Poly1305 class not found yet.");
  return hooked > 0;
}

function tryHookCompression() {
  let hooked = 0;

  const candidates = [
    ["System.IO.Compression.DeflateStream", ["Write", "Read"]],
    ["Ionic.Zlib.ZlibStream", ["Write", "Read"]],
    ["Ionic.Zlib.DeflateStream", ["Write", "Read"]],
  ];

  for (const [klassName, methods] of candidates) {
    const klass = (Il2Cpp && Il2Cpp.classes) ? Il2Cpp.classes[klassName] : null;
    if (!klass) continue;

    for (const mn of methods) {
      const ms = klass.methods.filter(m => m.name.indexOf(mn) >= 0);
      for (const m of ms) {
        const original = m.implementation;
        if (!original) continue;

        m.implementation = function () {
          try {
            let baseStream = null;
            const getBase = this.$class.methods.find(mm => mm.name.indexOf("get_BaseStream") >= 0);
            if (getBase) baseStream = getBase.invoke(this);
            if (!baseStream) {
              const fld = this.$class.fields.find(f =>
                ["_stream","stream","_baseStream","baseStream","_outStream"].includes(f.name));
              if (fld) baseStream = fld.value(this);
            }

            if (!baseStream) {
              if (LOG_VERBOSE) log(`${klassName}.${m.name}: no BaseStream found, leaving original.`);
              return original.apply(this, arguments);
            }

            const isWrite = m.name.indexOf("Write") >= 0;
            const isRead  = m.name.indexOf("Read")  >= 0;

            if (isWrite && arguments.length >= 3) {
              const buf   = arguments[0];
              const off   = arguments[1].toInt32 ? arguments[1].toInt32() : arguments[1];
              const count = arguments[2].toInt32 ? arguments[2].toInt32() : arguments[2];

              const writeM = baseStream.$class.methods.find(mm => mm.name === "Write");
              if (writeM) {
                writeM.invoke(baseStream, buf, off, count);
                if (LOG_VERBOSE) log(`${klassName}.Write passthrough ${count} bytes`);
                return;
              }
            }

            if (isRead && arguments.length >= 3) {
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

function installPollingHooks() {
  // Called once IL2CPP is usable (or as a passive fallback) – poll for late-loaded assemblies.
  let tries = 0;
  const maxTries = 15;
  const t = setInterval(() => {
    let c1 = false, c2 = false;
    try { c1 = tryHookChaCha(); } catch (e) { /* ignore */ }
    try { c2 = tryHookCompression(); } catch (e) { /* ignore */ }
    tries++;

    if ((c1 || tries >= maxTries) && (c2 || tries >= maxTries)) {
      clearInterval(t);
      log("Bypass installed (crypto:", !!c1, " compression:", !!c2, "). Login then flip proxy.");
    } else if (LOG_VERBOSE) {
      log("Retrying hooks…", tries);
    }
  }, 1000);
}

async function waitAndHook() {
  try {
    // Detect available API surface across bridge versions.
    const hasInitialize = Il2Cpp && typeof Il2Cpp.initialize === "function";
    const hasPerform    = Il2Cpp && typeof Il2Cpp.perform === "function";

    // Always wait for GameAssembly.dll to be present to avoid early failures.
    const needModule = "GameAssembly.dll";
    const start = Date.now();
    while (!Module.findBaseAddress(needModule) && Date.now() - start < 30000) {
      if (LOG_VERBOSE) log(`Waiting for ${needModule}...`);
      Thread.sleep(0.5);
    }
    const base = Module.findBaseAddress(needModule);
    if (!base) {
      log(`ERROR: ${needModule} not found; cannot proceed.`);
      return;
    }
    log(`${needModule} @ ${base}`);

    if (hasInitialize) {
      try {
        await Il2Cpp.initialize();
        log("Il2Cpp.initialize() OK");
      } catch (e) {
        log("Il2Cpp.initialize() threw; continuing with fallback:", e);
      }
    }

    if (hasPerform) {
      // Classic API: ensures IL2CPP world is ready.
      Il2Cpp.perform(() => {
        try { log("IL2CPP ready. Unity", Il2Cpp.unityVersion); } catch (_) { log("IL2CPP ready."); }
        installPollingHooks();
      });
    } else {
      // Fallback: no perform() in this bridge; start polling directly.
      log("frida-il2cpp-bridge has no perform(); using passive poll.");
      installPollingHooks();
    }
  } catch (e) {
    log("Hook bootstrap error:", e);
  }
}

waitAndHook();
