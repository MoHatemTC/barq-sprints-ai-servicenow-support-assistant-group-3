var HmacSha256 = Class.create();

HmacSha256.prototype = {

initialize: function() {},



/**

* Calculates a 64-character lowercase hex HMAC-SHA256 digest.

* @param {string} key - Signing secret

* @param {string} message - Exact stringified request body

* @returns {string} 64-character hex digest

*/

calculate: function(key, message) {

return this._hmacSha256(key || '', message || '');

},



_sha256Words: function(words, bitLength) {

var K = [

0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,

0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,

0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,

0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,

0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,

0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,

0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,

0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2

];

var H = [

0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,

0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19

];



words[bitLength >> 5] |= 0x80 << (24 - (bitLength % 32));

words[(((bitLength + 64) >> 9) << 4) + 15] = bitLength;



var W = new Array(64);

for (var i = 0; i < words.length; i += 16) {

for (var t = 0; t < 16; t++) {

W[t] = words[i + t] || 0;

}

for (var t = 16; t < 64; t++) {

var gamma0 = this._rotr(W[t - 15], 7) ^ this._rotr(W[t - 15], 18) ^ (W[t - 15] >>> 3);

var gamma1 = this._rotr(W[t - 2], 17) ^ this._rotr(W[t - 2], 19) ^ (W[t - 2] >>> 10);

W[t] = (W[t - 16] + gamma0 + W[t - 7] + gamma1) | 0;

}



var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];



for (var t = 0; t < 64; t++) {

var sigma1 = this._rotr(e, 6) ^ this._rotr(e, 11) ^ this._rotr(e, 25);

var ch = (e & f) ^ (~e & g);

var temp1 = (h + sigma1 + ch + K[t] + W[t]) | 0;

var sigma0 = this._rotr(a, 2) ^ this._rotr(a, 13) ^ this._rotr(a, 22);

var maj = (a & b) ^ (a & c) ^ (b & c);

var temp2 = (sigma0 + maj) | 0;



h = g;

g = f;

f = e;

e = (d + temp1) | 0;

d = c;

c = b;

b = a;

a = (temp1 + temp2) | 0;

}



H[0] = (H[0] + a) | 0;

H[1] = (H[1] + b) | 0;

H[2] = (H[2] + c) | 0;

H[3] = (H[3] + d) | 0;

H[4] = (H[4] + e) | 0;

H[5] = (H[5] + f) | 0;

H[6] = (H[6] + g) | 0;

H[7] = (H[7] + h) | 0;

}

return H;

},



_rotr: function(n, b) {

return (n >>> b) | (n << (32 - b));

},



_stringToUtf8Bytes: function(str) {

var bytes = [];

for (var i = 0; i < str.length; i++) {

var c = str.charCodeAt(i);

if (c < 128) {

bytes.push(c);

} else if (c < 2048) {

bytes.push((c >> 6) | 192);

bytes.push((c & 63) | 128);

} else if ((c & 0xFC00) === 0xD800 && i + 1 < str.length && (str.charCodeAt(i + 1) & 0xFC00) === 0xDC00) {

c = 0x10000 + ((c & 0x03FF) << 10) + (str.charCodeAt(++i) & 0x03FF);

bytes.push((c >> 18) | 240);

bytes.push(((c >> 12) & 63) | 128);

bytes.push(((c >> 6) & 63) | 128);

bytes.push((c & 63) | 128);

} else {

bytes.push((c >> 12) | 224);

bytes.push(((c >> 6) & 63) | 128);

bytes.push((c & 63) | 128);

}

}

return bytes;

},



_bytesToWords: function(bytes) {

var words = [];

for (var i = 0; i < bytes.length; i++) {

words[i >> 2] |= (bytes[i] & 0xFF) << (24 - (i % 4) * 8);

}

return words;

},



_wordsToBytes: function(words) {

var bytes = [];

for (var i = 0; i < words.length * 4; i++) {

bytes.push((words[i >> 2] >>> (24 - (i % 4) * 8)) & 0xFF);

}

return bytes;

},



_bytesToHex: function(bytes) {

var hex = [];

for (var i = 0; i < bytes.length; i++) {

var b = (bytes[i] & 0xFF).toString(16);

hex.push(b.length === 1 ? '0' + b : b);

}

return hex.join('');

},



_hmacSha256: function(key, message) {

var keyBytes = this._stringToUtf8Bytes(key);

var msgBytes = this._stringToUtf8Bytes(message);



if (keyBytes.length > 64) {

var keyWords = this._bytesToWords(keyBytes);

var hashedWords = this._sha256Words(keyWords, keyBytes.length * 8);

keyBytes = this._wordsToBytes(hashedWords);

}



while (keyBytes.length < 64) {

keyBytes.push(0);

}



var oPadBytes = [];

var iPadBytes = [];

for (var i = 0; i < 64; i++) {

oPadBytes[i] = keyBytes[i] ^ 0x5c;

iPadBytes[i] = keyBytes[i] ^ 0x36;

}



var innerBytes = iPadBytes.concat(msgBytes);

var innerWords = this._bytesToWords(innerBytes);

var innerHashWords = this._sha256Words(innerWords, innerBytes.length * 8);

var innerHashBytes = this._wordsToBytes(innerHashWords);



var outerBytes = oPadBytes.concat(innerHashBytes);

var outerWords = this._bytesToWords(outerBytes);

var outerHashWords = this._sha256Words(outerWords, outerBytes.length * 8);

var outerHashBytes = this._wordsToBytes(outerHashWords);



return this._bytesToHex(outerHashBytes);

},



type: 'HmacSha256'

};