#!/usr/bin/env python3
"""
Generate a markdown triage report for failed Azure DevOps builds, then post it
to GitHub as a comment (PR comment when available, else commit comment).

Required environment:
  - SYSTEM_COLLECTIONURI
  - SYSTEM_TEAMPROJECT
  - BUILD_BUILDID
  - BUILD_BUILDNUMBER
  - BUILD_DEFINITIONNAME
  - BUILD_SOURCEBRANCH
  - BUILD_SOURCEVERSION
  - BUILD_REPOSITORY_NAME
  - ADO_ACCESS_TOKEN (typically mapped from $(System.AccessToken))
  - OPENAI_API_KEY
  - GITHUB_TOKEN
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


TIMELINE_API_VERSION = "7.1-preview.1"
LOG_API_VERSION = "7.1-preview.2"
GITHUB_API_VERSION = "2022-11-28"
DEFAULT_MODEL = "gpt-5-mini"

INTERESTING_LINE_PATTERN = re.compile(
    r"(##\[error\]|error|exception|traceback|failed|fatal|panic|timed out|"
    r"permission denied|not found|exit code|segmentation fault)",
    re.IGNORECASE,
)


@dataclass
class FailedTask:
    task_name: str
    parent_name: str
    log_id: int
    excerpt_lines: List[Tuple[int, str]]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def require_env(name: str) -> str:
    value = env(name).strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def make_url(base: str, path: str, query: str) -> str:
    return f"{base.rstrip('/')}/{path}?{query}"


def build_project_api_base(collection_uri: str, project_name: str, project_id: str) -> str:
    """
    Build a reliable project-scoped API base URL.

    In some hosted agents SYSTEM_COLLECTIONURI can already include a project
    segment (name or GUID). If so, avoid appending project again.
    """
    base = collection_uri.rstrip("/")
    lowered = base.lower()
    project_name_l = project_name.lower()
    project_id_l = project_id.lower()

    if lowered.endswith(f"/{project_name_l}") or (project_id and lowered.endswith(f"/{project_id_l}")):
        return base

    project_segment = project_id.strip() or project_name.strip()
    return f"{base}/{project_segment}"


def http_json(
    url: str,
    token: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "sonic-buildimage-ci-triage",
    }
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def http_text(url: str, token: str) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/plain",
        "User-Agent": "sonic-buildimage-ci-triage",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def sanitize_line(line: str) -> str:
    # Hide very common token formats without aggressively masking normal logs.
    line = re.sub(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._-]+", r"\1***", line)
    line = re.sub(r"\b(gh[pousr]_[A-Za-z0-9]{20,})\b", "***", line)
    line = re.sub(r"\b([A-Za-z0-9]{52})\b", "***", line)
    return line


def truncate(value: str, max_len: int = 280) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def extract_excerpt_lines(log_text: str, max_lines: int) -> List[Tuple[int, str]]:
    lines = log_text.splitlines()
    picked: List[Tuple[int, str]] = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        if INTERESTING_LINE_PATTERN.search(line):
            picked.append((idx, truncate(sanitize_line(line))))
        if len(picked) >= max_lines:
            break

    if picked:
        return picked

    tail = [ln for ln in lines[-max_lines:] if ln.strip()]
    first_tail_line = max(1, len(lines) - len(tail) + 1)
    return [
        (first_tail_line + i, truncate(sanitize_line(line.strip())))
        for i, line in enumerate(tail)
    ]


def fetch_failed_tasks(
    project_api_base: str,
    project: str,
    build_id: str,
    ado_token: str,
    max_tasks: int,
    max_lines_per_task: int,
) -> List[FailedTask]:
    timeline_url = make_url(
        project_api_base,
        f"_apis/build/builds/{build_id}/timeline",
        f"api-version={TIMELINE_API_VERSION}",
    )
    timeline = http_json(timeline_url, ado_token)
    records = timeline.get("records", [])

    by_id = {r.get("id"): r for r in records if r.get("id")}
    failed_tasks: List[FailedTask] = []

    for record in records:
        if str(record.get("result", "")).lower() != "failed":
            continue
        log_obj = record.get("log") or {}
        log_id = log_obj.get("id")
        if not log_id:
            continue

        parent_name = ""
        parent_id = record.get("parentId")
        if parent_id and parent_id in by_id:
            parent_name = by_id[parent_id].get("name", "")

        log_url = make_url(
            project_api_base,
            f"_apis/build/builds/{build_id}/logs/{log_id}",
            f"api-version={LOG_API_VERSION}",
        )
        try:
            log_text = http_text(log_url, ado_token)
        except urllib.error.HTTPError as err:
            log_text = f"Failed to fetch log {log_id}: HTTP {err.code}"
        except Exception as err:
            log_text = f"Failed to fetch log {log_id}: {err}"

        failed_tasks.append(
            FailedTask(
                task_name=record.get("name", f"log-{log_id}"),
                parent_name=parent_name,
                log_id=int(log_id),
                excerpt_lines=extract_excerpt_lines(log_text, max_lines=max_lines_per_task),
            )
        )
        if len(failed_tasks) >= max_tasks:
            break

    return failed_tasks


def render_excerpts_markdown(tasks: List[FailedTask]) -> str:
    chunks: List[str] = []
    for i, task in enumerate(tasks, start=1):
        header = f"### {i}. {task.task_name}"
        if task.parent_name:
            header += f" (job: {task.parent_name})"
        lines = "\n".join(f"L{ln}: {txt}" for ln, txt in task.excerpt_lines)
        chunks.append(f"{header}\n\n```text\n{lines}\n```")
    return "\n\n".join(chunks)


def build_llm_prompt(meta: Dict[str, str], tasks: List[FailedTask]) -> str:
    task_blocks = []
    for i, task in enumerate(tasks, start=1):
        excerpt = "\n".join(f"L{ln}: {txt}" for ln, txt in task.excerpt_lines)
        task_blocks.append(
            textwrap.dedent(
                f"""\
                Failed task {i}
                - task: {task.task_name}
                - job: {task.parent_name or "n/a"}
                - logId: {task.log_id}
                - key excerpts:
                {excerpt}
                """
            ).strip()
        )

    task_text = "\n\n".join(task_blocks) if task_blocks else "No failed task logs were available."

    return textwrap.dedent(
        f"""\
        Build metadata:
        - build_id: {meta["build_id"]}
        - build_number: {meta["build_number"]}
        - definition: {meta["definition_name"]}
        - branch: {meta["branch"]}
        - commit: {meta["commit"]}
        - repo: {meta["repo"]}

        Failed task evidence:
        {task_text}
        """
    )


def run_codex_triage(model: str, api_key: str, prompt: str) -> str:
    if OpenAI is None:
        raise RuntimeError("openai package is unavailable. Install with: pip install openai")

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are a CI incident triage assistant for SONiC build pipelines.\n"
                            "Return markdown with these sections in order:\n"
                            "1) Summary\n"
                            "2) Likely Root Cause\n"
                            "3) Evidence From Logs (quote short excerpts)\n"
                            "4) Suggested Fixes (Immediate, Short-term, Long-term)\n"
                            "5) Confidence\n"
                            "Keep it concrete and technical. Do not invent facts not present in logs."
                        ),
                    }
                ],
            },
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ],
    )

    text = getattr(response, "output_text", "") or ""
    if text.strip():
        return text.strip()

    # Fallback for SDK response shape changes.
    try:
        raw = response.model_dump()
        return json.dumps(raw, indent=2)
    except Exception:
        return "Unable to parse model response."


def fallback_triage(tasks: List[FailedTask]) -> str:
    lines = [
        "## Summary",
        "Automated Codex analysis was unavailable. This report uses rule-based triage from failed task logs.",
        "",
        "## Likely Root Cause",
    ]
    if not tasks:
        lines.append("- No failed task logs were available. Check job-level cancellation/infra issues.")
    else:
        lines.append(
            "- One or more pipeline tasks failed. Review the error excerpts below and validate agent, dependency, and testbed setup."
        )
    lines.extend(
        [
            "",
            "## Suggested Fixes",
            "- Immediate: Re-run only after confirming the failed task preconditions (credentials, testbed, artifacts).",
            "- Short-term: Add retries or pre-flight checks around known flaky setup steps.",
            "- Long-term: Add runbook mappings from failure signatures to deterministic remediation actions.",
            "",
            "## Confidence",
            "- Low (fallback mode).",
        ]
    )
    return "\n".join(lines)


def write_report(
    output_path: str,
    meta: Dict[str, str],
    triage_markdown: str,
    excerpt_markdown: str,
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    report = textwrap.dedent(
        f"""\
        # CI Failure Triage Report

        - Build ID: `{meta["build_id"]}`
        - Build Number: `{meta["build_number"]}`
        - Definition: `{meta["definition_name"]}`
        - Branch: `{meta["branch"]}`
        - Commit: `{meta["commit"]}`
        - Repository: `{meta["repo"]}`
        - Generated At (UTC): `{generated_at}`

        {triage_markdown}

        ## Key Log Excerpts

        {excerpt_markdown if excerpt_markdown.strip() else "No failed task log excerpts were captured."}
        """
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    return report


def github_post_comment(
    github_token: str,
    repo_full_name: str,
    body: str,
    pr_number: str,
    commit_sha: str,
) -> Tuple[bool, str]:
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "sonic-buildimage-ci-triage",
        "Content-Type": "application/json",
    }

    if pr_number:
        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"
    elif commit_sha:
        url = f"https://api.github.com/repos/{repo_full_name}/commits/{commit_sha}/comments"
    else:
        return False, "Missing PR number and commit SHA; skipped GitHub comment."

    payload = json.dumps({"body": body}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            resp = json.loads(response.read().decode("utf-8", errors="replace"))
            html_url = resp.get("html_url", "")
            return True, f"Posted GitHub comment: {html_url}"
    except urllib.error.HTTPError as err:
        details = err.read().decode("utf-8", errors="replace")
        return False, f"GitHub comment failed: HTTP {err.code} {details}"
    except Exception as err:  # pragma: no cover
        return False, f"GitHub comment failed: {err}"


def build_comment_body(meta: Dict[str, str], triage_report: str) -> str:
    prefix = textwrap.dedent(
        f"""\
        ## CI Failure Triage (`{meta["build_number"]}`)

        Automated failure analysis generated by Codex SDK.

        - Build ID: `{meta["build_id"]}`
        - Branch: `{meta["branch"]}`
        - Commit: `{meta["commit"]}`
        """
    ).strip()

    comment = f"{prefix}\n\n{triage_report}"
    max_len = 60000
    if len(comment) > max_len:
        comment = comment[: max_len - 80] + "\n\n_Comment truncated due to size._"
    return comment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and post CI failure triage report.")
    parser.add_argument("--output", required=True, help="Output markdown path.")
    parser.add_argument("--model", default=env("OPENAI_MODEL", DEFAULT_MODEL), help="OpenAI model name.")
    parser.add_argument("--max-failed-tasks", type=int, default=6, help="Maximum failed tasks to inspect.")
    parser.add_argument("--max-lines-per-task", type=int, default=20, help="Maximum key lines per failed task.")
    parser.add_argument(
        "--post-github-comment",
        action="store_true",
        help="Post generated triage markdown to GitHub (PR or commit comment).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    collection_uri = require_env("SYSTEM_COLLECTIONURI")
    project = require_env("SYSTEM_TEAMPROJECT")
    project_id = env("SYSTEM_TEAMPROJECTID")
    build_id = require_env("BUILD_BUILDID")
    build_number = require_env("BUILD_BUILDNUMBER")
    definition_name = require_env("BUILD_DEFINITIONNAME")
    branch = require_env("BUILD_SOURCEBRANCH")
    commit = require_env("BUILD_SOURCEVERSION")
    repo = require_env("BUILD_REPOSITORY_NAME")
    ado_token = require_env("ADO_ACCESS_TOKEN")

    meta = {
        "build_id": build_id,
        "build_number": build_number,
        "definition_name": definition_name,
        "branch": branch,
        "commit": commit,
        "repo": repo,
    }

    project_api_base = build_project_api_base(collection_uri, project, project_id)

    failed_tasks = fetch_failed_tasks(
        project_api_base=project_api_base,
        project=project,
        build_id=build_id,
        ado_token=ado_token,
        max_tasks=args.max_failed_tasks,
        max_lines_per_task=args.max_lines_per_task,
    )

    llm_prompt = build_llm_prompt(meta, failed_tasks)
    openai_key = env("OPENAI_API_KEY").strip()
    if openai_key:
        try:
            triage_markdown = run_codex_triage(args.model, openai_key, llm_prompt)
        except Exception as err:
            triage_markdown = (
                f"## Summary\nCodex triage failed: `{err}`\n\n" + fallback_triage(failed_tasks)
            )
    else:
        triage_markdown = (
            "## Summary\nOPENAI_API_KEY is not configured; generated fallback triage only.\n\n"
            + fallback_triage(failed_tasks)
        )

    excerpt_markdown = render_excerpts_markdown(failed_tasks)
    full_report = write_report(args.output, meta, triage_markdown, excerpt_markdown)
    print(f"Wrote triage report: {args.output}")

    if args.post_github_comment:
        github_token = env("GITHUB_TOKEN").strip()
        if not github_token:
            print("GITHUB_TOKEN is not configured; skipped posting GitHub comment.")
            return 0

        pr_number = env("SYSTEM_PULLREQUEST_PULLREQUESTNUMBER").strip()
        comment_body = build_comment_body(meta, full_report)
        ok, message = github_post_comment(
            github_token=github_token,
            repo_full_name=repo,
            body=comment_body,
            pr_number=pr_number,
            commit_sha=commit,
        )
        print(message)
        if not ok:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
