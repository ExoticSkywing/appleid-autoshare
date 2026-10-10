// Pure JavaScript SHA-256 implementation fallback for non-secure contexts (plain HTTP IP access)
function sha256_js(ascii) {
  function rightRotate(value, amount) {
    return (value >>> amount) | (value << (32 - amount));
  }
  const mathPow = Math.pow;
  const maxWord = mathPow(2, 32);
  let lengthProperty = "length";
  let i, j;
  let result = "";
  const words = [];
  const asciiBitLength = ascii[lengthProperty] * 8;
  let hash = [];
  const k = [];
  let primeCounter = 0;

  const isComposite = {};
  for (let candidate = 2; primeCounter < 64; candidate++) {
    if (!isComposite[candidate]) {
      for (i = 0; i < 313; i += candidate) {
        isComposite[i] = candidate;
      }
      hash[primeCounter] = (mathPow(candidate, 0.5) * maxWord) | 0;
      k[primeCounter++] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
    }
  }

  ascii += "\x80";
  while ((ascii[lengthProperty] % 64) - 56) ascii += "\x00";
  for (i = 0; i < ascii[lengthProperty]; i++) {
    j = ascii.charCodeAt(i);
    if (j >> 8) return;
    words[i >> 2] |= j << (((3 - i) % 4) * 8);
  }
  words[words[lengthProperty]] = (asciiBitLength / maxWord) | 0;
  words[words[lengthProperty]] = asciiBitLength | 0;

  for (j = 0; j < words[lengthProperty]; ) {
    const w = words.slice(j, (j += 16));
    const oldHash = hash;
    hash = hash.slice(0, 8);

    for (i = 0; i < 64; i++) {
      const i2 = i + j;
      const w15 = w[i - 15],
        w2 = w[i - 2];
      const a = hash[0],
        e = hash[4];
      const temp1 =
        hash[7] +
        (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25)) +
        ((e & hash[5]) ^ (~e & hash[6])) +
        k[i] +
        (w[i] =
          i < 16
            ? w[i]
            : (w[i - 16] +
                (rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15 >>> 3)) +
                w[i - 7] +
                (rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2 >>> 10))) |
              0);
      const temp2 =
        (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22)) +
        ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));

      hash = [(temp1 + temp2) | 0].concat(hash);
      hash[4] = (hash[4] + temp1) | 0;
    }

    for (i = 0; i < 8; i++) {
      hash[i] = (hash[i] + oldHash[i]) | 0;
    }
  }

  for (i = 0; i < 8; i++) {
    for (i2 = 3; i2 >= 0; i2--) {
      const c = (hash[i] >> (i2 * 8)) & 255;
      result += (c < 16 ? "0" : "") + c.toString(16);
    }
  }
  return result;
}

self.onmessage = async function(e) {
  try {
    const { challenge, salt, maxnumber } = e.data;
    const max = maxnumber || 40000;
    const start = performance.now();
    const hasSubtle = typeof crypto !== "undefined" && Boolean(crypto.subtle);

    if (hasSubtle) {
      const enc = new TextEncoder();
      for (let n = 0; n <= max; n++) {
        const data = enc.encode(salt + n);
        const hashBuf = await crypto.subtle.digest("SHA-256", data);
        const hashArray = Array.from(new Uint8Array(hashBuf));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
        if (hashHex === challenge) {
          self.postMessage({
            success: true,
            solution: n,
            took: Math.round(performance.now() - start),
          });
          return;
        }
      }
    } else {
      // HTTP / Non-secure context pure JS fallback
      for (let n = 0; n <= max; n++) {
        if (sha256_js(salt + n) === challenge) {
          self.postMessage({
            success: true,
            solution: n,
            took: Math.round(performance.now() - start),
          });
          return;
        }
      }
    }
    self.postMessage({ success: false, error: "max_reached" });
  } catch (err) {
    self.postMessage({ success: false, error: String(err) });
  }
};
