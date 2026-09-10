from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import os
import re

# Default Asymmetry Railway project (asymmetry-surface).
RAILWAY_PROJECT_ID = os.getenv(
    "RAILWAY_PROJECT_ID", "b0ae0d89-e082-437c-98d6-05733e494990"
)
RAILWAY_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _railway_graphql(query: str, variables: dict | None = None) -> dict:
    """POST a GraphQL query to Railway using RAILWAY_TOKEN (Bearer)."""
    token = os.getenv("RAILWAY_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "RAILWAY_TOKEN is not set. Add an account or workspace Railway API "
            "token to the environment (Bearer auth)."
        )

    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    req = Request(
        RAILWAY_GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "AsymmetryRailwayLogs/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("errors"):
        messages = "; ".join(e.get("message", str(e)) for e in body["errors"])
        raise RuntimeError(f"Railway API error: {messages}")
    return body.get("data") or {}


class FetchRailwayLogs(BaseTool):
    """
    Fetch recent Railway build or runtime logs for Asymmetry (tier-2 visibility).
    Defaults to the latest deployment in the production environment. Use after
    CheckRailwayStatus shows FAILED/CRASHED/IN_PROGRESS, or when a tester's
    outage needs a short log excerpt for diagnosis. Requires RAILWAY_TOKEN.
    Read-only; returns a truncated plain-text excerpt (not a full log dump).
    """

    environment: str = Field(
        default="production",
        description="Railway environment name to pull the latest deployment from.",
    )
    log_type: str = Field(
        default="runtime",
        description="Which logs to fetch: 'runtime' (deploymentLogs) or 'build' (buildLogs).",
    )
    deployment_id: str = Field(
        default="",
        description=(
            "Optional specific deployment ID. If empty, uses the most recent "
            "deployment in the chosen environment."
        ),
    )
    max_lines: int = Field(
        default=40,
        description="Maximum number of log lines to return (most recent tail).",
    )

    def run(self) -> str:
        checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        project_id = RAILWAY_PROJECT_ID
        log_type = self.log_type.strip().lower()
        if log_type not in {"runtime", "build"}:
            return (
                f"Railway logs: invalid log_type '{self.log_type}'. "
                "Use 'runtime' or 'build'."
            )

        try:
            deploy_id = self.deployment_id.strip()
            deploy_meta = ""

            if not deploy_id:
                # Resolve environment id, then pick the latest deployment.
                proj = _railway_graphql(
                    """
                    query project($id: String!) {
                      project(id: $id) {
                        name
                        environments { edges { node { id name } } }
                      }
                    }
                    """,
                    {"id": project_id},
                ).get("project")
                if not proj:
                    return (
                        f"Railway logs: UNAVAILABLE at {checked_at} "
                        f"(project {project_id} not accessible)."
                    )
                env_name = self.environment.strip().lower()
                env = next(
                    (
                        e["node"]
                        for e in proj.get("environments", {}).get("edges", [])
                        if e.get("node") and e["node"]["name"].lower() == env_name
                    ),
                    None,
                )
                if not env:
                    return (
                        f"Railway logs: unknown environment '{self.environment}' "
                        f"for project '{proj['name']}' at {checked_at}."
                    )

                deps = _railway_graphql(
                    """
                    query($input: DeploymentListInput!, $first: Int) {
                      deployments(input: $input, first: $first) {
                        edges {
                          node { id status createdAt staticUrl }
                        }
                      }
                    }
                    """,
                    {
                        "input": {
                            "projectId": project_id,
                            "environmentId": env["id"],
                        },
                        "first": 1,
                    },
                )
                edges = deps.get("deployments", {}).get("edges", [])
                if not edges:
                    return (
                        f"Railway logs: no deployments in '{env['name']}' "
                        f"for project '{proj['name']}' at {checked_at}."
                    )
                node = edges[0]["node"]
                deploy_id = node["id"]
                deploy_meta = (
                    f"status={node.get('status')}, created={node.get('createdAt')}"
                    + (f", url={node.get('staticUrl')}" if node.get("staticUrl") else "")
                )

            # Step 1: Fetch the requested log stream.
            if log_type == "build":
                data = _railway_graphql(
                    """
                    query($deploymentId: String!) {
                      buildLogs(deploymentId: $deploymentId) { message }
                    }
                    """,
                    {"deploymentId": deploy_id},
                )
                raw_lines = [
                    _strip_ansi((entry or {}).get("message", ""))
                    for entry in data.get("buildLogs") or []
                ]
            else:
                data = _railway_graphql(
                    """
                    query($deploymentId: String!) {
                      deploymentLogs(deploymentId: $deploymentId) {
                        message
                        severity
                        timestamp
                      }
                    }
                    """,
                    {"deploymentId": deploy_id},
                )
                raw_lines = []
                for entry in data.get("deploymentLogs") or []:
                    entry = entry or {}
                    msg = _strip_ansi(entry.get("message", "")).rstrip()
                    if not msg:
                        continue
                    ts = entry.get("timestamp") or ""
                    sev = entry.get("severity") or ""
                    prefix = " ".join(p for p in (ts, sev) if p)
                    raw_lines.append(f"{prefix}: {msg}" if prefix else msg)

            # Step 2: Keep only the tail and drop empty lines.
            cleaned = [ln for ln in raw_lines if ln.strip()]
            limit = max(1, min(int(self.max_lines), 200))
            tail = cleaned[-limit:]

            header = (
                f"Railway {log_type} logs for deployment {deploy_id} "
                f"at {checked_at}"
                + (f" ({deploy_meta})" if deploy_meta else "")
                + f" — showing last {len(tail)} of {len(cleaned)} lines."
            )
            if not tail:
                return header + "\n(no log lines returned)"

            # Cap total characters so we don't blow the agent's context.
            body = "\n".join(tail)
            if len(body) > 6000:
                body = "…\n" + body[-6000:]
            return header + "\n" + body

        except (RuntimeError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            return f"Railway logs: UNAVAILABLE at {checked_at} (error: {e})."


if __name__ == "__main__":
    print(FetchRailwayLogs(log_type="runtime", max_lines=20).run())
    print("---")
    print(FetchRailwayLogs(log_type="build", max_lines=20).run())
