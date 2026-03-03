/**
 * Encrypted API Key Storage using Electron's safeStorage.
 *
 * Keys are encrypted with the OS credential store (DPAPI on Windows,
 * Keychain on macOS, libsecret on Linux) and persisted as base64 in
 * data/keys.enc.json.
 *
 * Falls back to plaintext .env files if safeStorage is unavailable.
 */

const { safeStorage } = require('electron');
const fs = require('fs');
const path = require('path');

const KEYS_FILE = path.join(__dirname, '..', '..', 'data', 'keys.enc.json');

// Ensure data directory exists
function ensureDataDir() {
  const dir = path.dirname(KEYS_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function readKeysFile() {
  try {
    if (fs.existsSync(KEYS_FILE)) {
      return JSON.parse(fs.readFileSync(KEYS_FILE, 'utf8'));
    }
  } catch (e) {
    console.error('Failed to read keys file:', e.message);
  }
  return {};
}

function writeKeysFile(data) {
  ensureDataDir();
  fs.writeFileSync(KEYS_FILE, JSON.stringify(data, null, 2), 'utf8');
}

/**
 * Save an API key for a provider (encrypted).
 * @param {string} provider - e.g. "GROQ_API_KEY"
 * @param {string} key - the plaintext API key
 */
function saveApiKey(provider, key) {
  if (!provider || !key) return false;

  const keys = readKeysFile();

  if (safeStorage.isEncryptionAvailable()) {
    const encrypted = safeStorage.encryptString(key);
    keys[provider] = encrypted.toString('base64');
  } else {
    // Fallback: store as plaintext (not ideal, but functional)
    keys[provider] = { plaintext: key };
  }

  writeKeysFile(keys);
  return true;
}

/**
 * Get a decrypted API key for a provider.
 * @param {string} provider - e.g. "GROQ_API_KEY"
 * @returns {string|null} decrypted key or null
 */
function getApiKey(provider) {
  const keys = readKeysFile();
  const stored = keys[provider];

  if (!stored) return null;

  // Handle plaintext fallback
  if (typeof stored === 'object' && stored.plaintext) {
    return stored.plaintext;
  }

  // Encrypted value (base64 string)
  if (typeof stored === 'string' && safeStorage.isEncryptionAvailable()) {
    try {
      const buffer = Buffer.from(stored, 'base64');
      return safeStorage.decryptString(buffer);
    } catch (e) {
      console.error('Failed to decrypt key for', provider, ':', e.message);
      return null;
    }
  }

  return null;
}

/**
 * Get all stored API keys (decrypted).
 * @returns {Object} {PROVIDER_ENV_VAR: decryptedKey, ...}
 */
function getAllApiKeys() {
  const keys = readKeysFile();
  const result = {};

  for (const [provider, stored] of Object.entries(keys)) {
    if (typeof stored === 'object' && stored.plaintext) {
      result[provider] = stored.plaintext;
    } else if (typeof stored === 'string' && safeStorage.isEncryptionAvailable()) {
      try {
        const buffer = Buffer.from(stored, 'base64');
        result[provider] = safeStorage.decryptString(buffer);
      } catch (e) {
        console.error('Failed to decrypt key for', provider);
      }
    }
  }

  return result;
}

/**
 * Remove an API key for a provider.
 * @param {string} provider - e.g. "GROQ_API_KEY"
 */
function removeApiKey(provider) {
  const keys = readKeysFile();
  delete keys[provider];
  writeKeysFile(keys);
}

/**
 * Check which providers have stored keys.
 * @returns {string[]} array of provider env var names
 */
function getConfiguredProviders() {
  const keys = readKeysFile();
  return Object.keys(keys);
}

module.exports = {
  saveApiKey,
  getApiKey,
  getAllApiKeys,
  removeApiKey,
  getConfiguredProviders,
};
