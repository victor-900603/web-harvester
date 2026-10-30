from __future__ import annotations

SUPPORTED_HTTP_CLIENTS = ("curl_cffi", "httpx")

# curl_cffi impersonate targets (subset most commonly used;
# curl_cffi accepts any string and will error at runtime if unknown,
# so validation is intentionally permissive but enumerated for schema).
SUPPORTED_IMPERSONATES = (
    "chrome99",
    "chrome100",
    "chrome101",
    "chrome104",
    "chrome107",
    "chrome110",
    "chrome116",
    "chrome119",
    "chrome120",
    "chrome122",
    "chrome124",
    "chrome131",
    "chrome131_android",
    "safari15_3",
    "safari15_5",
    "safari17_0",
    "safari17_2_ios",
    "safari18_0",
    "safari18_0_ios",
    "firefox133",
    "edge101",
    "edge122",
    "",
)
