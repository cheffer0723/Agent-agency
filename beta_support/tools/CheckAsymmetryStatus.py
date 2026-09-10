from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import os
import time

# The public Asymmetry endpoint to health-check. Overridable via env so the same
# tool can point at staging or a specific service URL without code changes.
ASYMMETRY_BASE_URL = os.getenv("ASYMMETRY_STATUS_URL", "https://asymmetria.io")


class CheckAsymmetryStatus(BaseTool):
    """
    Check whether the live Asymmetry service is currently reachable. Performs a
    lightweight HTTP GET against the public site and reports up/down, the HTTP
    status code, and response latency. Use this when a tester reports an outage
    or asks whether the service is working, so you can answer from real-time
    reality instead of guessing. This is a read-only availability check; it does
    NOT prove that internal features (e.g. payload delivery) are healthy.
    """

    path: str = Field(
        default="/",
        description="Path to check on the Asymmetry host, e.g. '/' or '/health'.",
    )
    timeout_seconds: int = Field(
        default=10, description="How long to wait before treating the site as unreachable."
    )

    def run(self) -> str:
        url = ASYMMETRY_BASE_URL.rstrip("/") + "/" + self.path.lstrip("/")
        checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        # Use a GET with a normal UA; some hosts reject default urllib headers.
        req = Request(url, method="GET", headers={"User-Agent": "AsymmetryStatusCheck/1.0"})

        start = time.monotonic()
        try:
            with urlopen(req, timeout=self.timeout_seconds) as resp:
                latency_ms = round((time.monotonic() - start) * 1000)
                code = resp.getcode()
                up = 200 <= code < 400
                return (
                    f"Asymmetry status: {'UP' if up else 'DEGRADED'} "
                    f"(HTTP {code}, {latency_ms} ms) for {url} at {checked_at}."
                )
        except HTTPError as e:
            latency_ms = round((time.monotonic() - start) * 1000)
            # A 4xx/5xx still means the server responded.
            up = 200 <= e.code < 400
            return (
                f"Asymmetry status: {'UP' if up else 'DEGRADED'} "
                f"(HTTP {e.code}, {latency_ms} ms) for {url} at {checked_at}."
            )
        except (URLError, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            return (
                f"Asymmetry status: DOWN/UNREACHABLE for {url} at {checked_at} "
                f"(error: {reason}). Note: pre-beta downtime is expected."
            )


if __name__ == "__main__":
    print(CheckAsymmetryStatus().run())
    print(CheckAsymmetryStatus(path="/definitely-not-a-real-path").run())
