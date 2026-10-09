// High-performance background Web Worker for SHA-256 Proof-of-Work
self.onmessage = async function(e) {
  const { challenge, salt, maxnumber } = e.data;
  const enc = new TextEncoder();
  const max = maxnumber || 50000;
  const start = performance.now();
  
  // Convert hex challenge string to byte values or compare string
  for (let n = 0; n <= max; n++) {
    const data = enc.encode(salt + n);
    const hashBuf = await crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuf));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
    if (hashHex === challenge) {
      self.postMessage({
        ok: true,
        number: n,
        took: Math.round(performance.now() - start),
      });
      return;
    }
  }
  self.postMessage({ ok: false, error: "max_reached" });
};
