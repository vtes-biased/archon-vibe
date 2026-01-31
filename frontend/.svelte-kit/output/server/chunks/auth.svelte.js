import "clsx";
const ACCESS_TOKEN_KEY = "archon_access_token";
let authState = {
  user: null,
  authMethods: [],
  isAuthenticated: false,
  isLoading: true,
  error: null
};
function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}
function getAuthState() {
  return authState;
}
function hasAnyRole(...roles) {
  return false;
}
function isPasskeySupported() {
  return typeof window !== "undefined" && window.PublicKeyCredential !== void 0 && typeof window.PublicKeyCredential === "function";
}
export {
  getAccessToken as a,
  getAuthState as g,
  hasAnyRole as h,
  isPasskeySupported as i
};
//# sourceMappingURL=auth.svelte.js.map
