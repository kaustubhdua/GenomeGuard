// Minimal browser OIDC Authorization Code + PKCE client.
// Access tokens remain in memory only. The API independently validates JWT signatures,
// issuer, audience, expiry and the signed organization claim on every request.
const TRANSACTION_KEY = "gg_oidc_transaction";

function encode64url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decode64url(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(normalized + "=".repeat((4 - normalized.length % 4) % 4));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function decodeJsonPart(value) {
  return JSON.parse(new TextDecoder().decode(decode64url(value)));
}

function randomVerifier() {
  return encode64url(crypto.getRandomValues(new Uint8Array(48)));
}

async function discover(issuer) {
  if (!issuer.startsWith("https://")) throw new Error("Institutional issuer must use HTTPS.");
  const response = await fetch(issuer.replace(/\/$/, "") + "/.well-known/openid-configuration", {
    headers: { Accept: "application/json" }, credentials: "omit", cache: "no-store",
  });
  if (!response.ok) throw new Error("The institution's OIDC discovery endpoint is unavailable.");
  const metadata = await response.json();
  if (metadata.issuer !== issuer) throw new Error("OIDC discovery issuer does not exactly match configuration.");
  for (const name of ["authorization_endpoint", "token_endpoint", "jwks_uri"]) {
    if (typeof metadata[name] !== "string" || !metadata[name].startsWith("https://")) {
      throw new Error("The OIDC provider has an invalid " + name + ".");
    }
  }
  if (!Array.isArray(metadata.response_types_supported)
      || !metadata.response_types_supported.includes("code")) {
    throw new Error("The OIDC provider does not advertise authorization-code flow.");
  }
  if (!Array.isArray(metadata.code_challenge_methods_supported)
      || !metadata.code_challenge_methods_supported.includes("S256")) {
    throw new Error("The OIDC provider must support PKCE S256.");
  }
  return metadata;
}

async function verifyIdToken(token, metadata, clientId, expectedNonce) {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("The institution returned a malformed ID token.");
  const header = decodeJsonPart(parts[0]);
  const claims = decodeJsonPart(parts[1]);
  if (!["RS256", "ES256"].includes(header.alg) || !header.kid) {
    throw new Error("The institution used an unsupported ID-token signing algorithm.");
  }
  if (claims.iss !== metadata.issuer || claims.nonce !== expectedNonce
      || typeof claims.sub !== "string" || !claims.sub) {
    throw new Error("The institution's ID token failed issuer, subject or nonce validation.");
  }
  const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!audiences.includes(clientId) || (audiences.length > 1 && claims.azp !== clientId)
      || (claims.azp && claims.azp !== clientId)) {
    throw new Error("The institution's ID token has the wrong audience.");
  }
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(claims.exp) || claims.exp <= now
      || !Number.isFinite(claims.iat) || claims.iat > now + 60) {
    throw new Error("The institution's ID token is expired or has an invalid issue time.");
  }

  const jwksResponse = await fetch(metadata.jwks_uri, {
    headers: { Accept: "application/json" }, credentials: "omit", cache: "no-store",
  });
  if (!jwksResponse.ok) throw new Error("Could not retrieve the institution's signing keys.");
  const jwks = await jwksResponse.json();
  const jwk = (jwks.keys || []).find((item) => item.kid === header.kid && item.use !== "enc");
  if (!jwk || (jwk.alg && jwk.alg !== header.alg)) {
    throw new Error("The institution's ID-token signing key was not found or did not match.");
  }
  let key;
  let algorithm;
  if (header.alg === "RS256" && jwk.kty === "RSA") {
    key = await crypto.subtle.importKey(
      "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"],
    );
    algorithm = { name: "RSASSA-PKCS1-v1_5" };
  } else if (header.alg === "ES256" && jwk.kty === "EC" && jwk.crv === "P-256") {
    key = await crypto.subtle.importKey(
      "jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"],
    );
    algorithm = { name: "ECDSA", hash: "SHA-256" };
  } else {
    throw new Error("The institution's signing key type does not match its token algorithm.");
  }
  const valid = await crypto.subtle.verify(
    algorithm, key, decode64url(parts[2]),
    new TextEncoder().encode(parts[0] + "." + parts[1]),
  );
  if (!valid) throw new Error("The institution's ID-token signature is invalid.");
  return claims;
}

export async function beginOidcLogin(config) {
  if (!config?.enabled || !config.client_id || !config.redirect_uri || !config.audience) {
    throw new Error("Institutional sign-in is not configured for this deployment.");
  }
  const metadata = await discover(config.issuer);
  const verifier = randomVerifier();
  const challenge = encode64url(new Uint8Array(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)),
  ));
  const state = randomVerifier();
  const nonce = randomVerifier();
  sessionStorage.setItem(TRANSACTION_KEY, JSON.stringify({
    state, nonce, verifier, issuer: config.issuer, clientId: config.client_id,
    redirectUri: config.redirect_uri,
  }));
  const url = new URL(metadata.authorization_endpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", config.client_id);
  url.searchParams.set("redirect_uri", config.redirect_uri);
  url.searchParams.set("scope", config.scopes || "openid profile email");
  url.searchParams.set("state", state);
  url.searchParams.set("nonce", nonce);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  window.location.assign(url.toString());
}

export async function completeOidcCallback(config) {
  const url = new URL(window.location.href);
  const code = url.searchParams.get("code");
  const error = url.searchParams.get("error");
  if (!code && !error) return null;
  const raw = sessionStorage.getItem(TRANSACTION_KEY);
  sessionStorage.removeItem(TRANSACTION_KEY);
  const cleanUrl = url.pathname + url.hash;
  window.history.replaceState({}, document.title, cleanUrl);
  if (!raw) throw new Error("The sign-in transaction expired. Please start again.");
  const transaction = JSON.parse(raw);
  if (error) throw new Error("Institutional sign-in failed: " + (url.searchParams.get("error_description") || error));
  if (url.searchParams.get("state") !== transaction.state
      || transaction.issuer !== config.issuer
      || transaction.clientId !== config.client_id
      || transaction.redirectUri !== config.redirect_uri) {
    throw new Error("The sign-in state did not match this browser session.");
  }

  const metadata = await discover(config.issuer);
  const responseIssuer = url.searchParams.get("iss");
  if ((responseIssuer && responseIssuer !== config.issuer)
      || (metadata.authorization_response_iss_parameter_supported && !responseIssuer)) {
    throw new Error("The authorization response issuer did not match the configured institution.");
  }
  const form = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.client_id,
    code,
    redirect_uri: config.redirect_uri,
    code_verifier: transaction.verifier,
  });
  const response = await fetch(metadata.token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: form.toString(),
    credentials: "omit",
    cache: "no-store",
  });
  const tokens = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error("The institution could not exchange the authorization code.");
  if (tokens.token_type?.toLowerCase() !== "bearer" || !tokens.access_token || !tokens.id_token) {
    throw new Error("The institution returned an incomplete OIDC token response.");
  }
  await verifyIdToken(tokens.id_token, metadata, config.client_id, transaction.nonce);
  if (tokens.access_token.split(".").length !== 3) {
    throw new Error("The institution must issue a signed JWT access token for the GenomeGuard API.");
  }
  return tokens.access_token;
}
