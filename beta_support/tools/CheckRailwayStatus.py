from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import os

# Default Asymmetry Railway project (asymmetry-surface). Overridable via env so
# the same tool can point at another project without code changes.
RAILWAY_PROJECT_ID = os.getenv(
    "RAILWAY_PROJECT_ID", "b0ae0d89-e082-437c-98d6-05733e494990"
)
RAILWAY_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

# Statuses that mean the deployment is not serving traffic healthily.
UNHEALTHY_STATUSES = {"FAILED", "CRASHED", "REMOVED", "SKIPPED"}
IN_PROGRESS_STATUSES = {"BUILDING", "DEPLOYING", "QUEUED", "WAITING"}
HEALTHY_STATUSES = {"SUCCESS", "SLEEPING"}


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

    # Cloudflare blocks bare urllib clients; a normal UA is required.
    req = Request(
        RAILWAY_GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "AsymmetryRailwayStatus/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("errors"):
        messages = "; ".join(e.get("message", str(e)) for e in body["errors"])
        raise RuntimeError(f"Railway API error: {messages}")
    return body.get("data") or {}


class CheckRailwayStatus(BaseTool):
    """
    Check live Railway deploy health for the Asymmetry project (tier-2 visibility).
    Reports each service's latest deployment status in the chosen environment
    (default: production), plus recent deploy outcomes. Use this when public
    HTTP checks are not enough — e.g. the site is down, a tester reports an
    outage, or you need to know whether the latest deploy succeeded, failed,
    or crashed. Requires RAILWAY_TOKEN. Read-only.
    """

    environment: str = Field(
        default="production",
        description=(
            "Railway environment name to inspect (e.g. 'production'). "
            "Case-insensitive match against environment names in the project."
        ),
    )
    recent_limit: int = Field(
        default=5,
        description="How many recent deployments (across the environment) to include.",
    )

    def run(self) -> str:
        checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        project_id = RAILWAY_PROJECT_ID

        try:
            data = _railway_graphql(
                """
                query project($id: String!) {
                  project(id: $id) {
                    id
                    name
                    environments { edges { node { id name } } }
                    services {
                      edges {
                        node {
                          id
                          name
                          serviceInstances {
                            edges {
                              node {
                                environmentId
                                domains {
                                  serviceDomains { domain }
                                  customDomains { domain }
                                }
                                latestDeployment {
                                  id
                                  status
                                  createdAt
                                  staticUrl
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
                """,
                {"id": project_id},
            )
        except (RuntimeError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            return (
                f"Railway status: UNAVAILABLE at {checked_at} "
                f"(could not query project {project_id}: {e})."
            )

        project = (data or {}).get("project")
        if not project:
            return (
                f"Railway status: UNAVAILABLE at {checked_at} "
                f"(project {project_id} not found or not accessible with RAILWAY_TOKEN)."
            )

        env_name = self.environment.strip().lower()
        env_map = {
            e["node"]["name"].lower(): e["node"]
            for e in project.get("environments", {}).get("edges", [])
            if e.get("node")
        }
        env = env_map.get(env_name)
        if not env:
            available = ", ".join(sorted(env_map.keys())) or "(none)"
            return (
                f"Railway status: unknown environment '{self.environment}' for "
                f"project '{project['name']}' ({project_id}) at {checked_at}. "
                f"Available: {available}."
            )

        # Step 1: Collect latest deployment per service in this environment.
        service_lines: list[str] = []
        worst = "HEALTHY"
        for edge in project.get("services", {}).get("edges", []):
            svc = edge.get("node") or {}
            match = None
            for inst_edge in svc.get("serviceInstances", {}).get("edges", []):
                inst = inst_edge.get("node") or {}
                if inst.get("environmentId") == env["id"]:
                    match = inst
                    break
            if not match:
                continue

            latest = match.get("latestDeployment")
            domains = []
            for d in (match.get("domains") or {}).get("serviceDomains") or []:
                if d.get("domain"):
                    domains.append(d["domain"])
            for d in (match.get("domains") or {}).get("customDomains") or []:
                if d.get("domain"):
                    domains.append(d["domain"])
            if latest and latest.get("staticUrl"):
                domains.append(latest["staticUrl"])
            # Deduplicate while preserving order.
            seen = set()
            domains = [d for d in domains if not (d in seen or seen.add(d))]

            if not latest:
                service_lines.append(
                    f"- {svc.get('name', '?')}: NO DEPLOYMENT"
                    + (f" ({', '.join(domains)})" if domains else "")
                )
                if worst == "HEALTHY":
                    worst = "UNKNOWN"
                continue

            status = (latest.get("status") or "UNKNOWN").upper()
            if status in UNHEALTHY_STATUSES:
                worst = "UNHEALTHY"
            elif status in IN_PROGRESS_STATUSES and worst == "HEALTHY":
                worst = "IN_PROGRESS"

            service_lines.append(
                f"- {svc.get('name', '?')}: {status} "
                f"(deploy {latest.get('id', '?')[:8]}…, "
                f"created {latest.get('createdAt', '?')})"
                + (f" → {', '.join(domains)}" if domains else "")
            )

        # Step 2: Recent deployments in this environment for trend context.
        recent_lines: list[str] = []
        try:
            dep_data = _railway_graphql(
                """
                query($input: DeploymentListInput!, $first: Int) {
                  deployments(input: $input, first: $first) {
                    edges {
                      node {
                        id
                        status
                        createdAt
                        staticUrl
                        serviceId
                        meta
                      }
                    }
                  }
                }
                """,
                {
                    "input": {
                        "projectId": project_id,
                        "environmentId": env["id"],
                    },
                    "first": max(1, min(int(self.recent_limit), 20)),
                },
            )
            # Map serviceId -> name for readable recent lines.
            svc_names = {
                e["node"]["id"]: e["node"]["name"]
                for e in project.get("services", {}).get("edges", [])
                if e.get("node")
            }
            for edge in dep_data.get("deployments", {}).get("edges", []):
                node = edge.get("node") or {}
                meta = node.get("meta") or {}
                commit = (meta.get("commitHash") or "")[:7]
                msg = (meta.get("commitMessage") or "").splitlines()[0][:60]
                svc_label = svc_names.get(node.get("serviceId"), node.get("serviceId", "?")[:8])
                recent_lines.append(
                    f"- {node.get('status', '?')} {svc_label} "
                    f"at {node.get('createdAt', '?')}"
                    + (f" ({commit}" + (f" {msg}" if msg else "") + ")" if commit else "")
                    + (f" [{node.get('staticUrl')}]" if node.get("staticUrl") else "")
                )
        except (RuntimeError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            recent_lines.append(f"(could not list recent deployments: {e})")

        if not service_lines:
            service_lines.append("- (no services found in this environment)")

        summary = (
            f"Railway status: {worst} for project '{project['name']}' "
            f"({project_id}), environment '{env['name']}', checked at {checked_at}."
        )
        parts = [
            summary,
            "",
            "Latest deployment per service:",
            *service_lines,
            "",
            f"Recent deployments (last {self.recent_limit}):",
            *(recent_lines or ["- (none)"]),
            "",
            "Note: this is Railway deploy health, not a proof that every product "
            "feature works. Pair with CheckAsymmetryStatus for public reachability.",
        ]
        return "\n".join(parts)


if __name__ == "__main__":
    print(CheckRailwayStatus().run())
    print("---")
    print(CheckRailwayStatus(environment="production", recent_limit=3).run())
