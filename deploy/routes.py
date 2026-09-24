# Prefixes the app vhost proxies to the backend; everything else is the SPA.
BACKEND_PATHS = (
    "/api",
    "/auth",
    "/oauth",
    "/vekn",
    "/sanctions",
    "/admin",
    "/snapshot",
)
SSE_PATH = "/stream"
