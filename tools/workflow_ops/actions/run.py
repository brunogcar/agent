"""tools/workflow_ops/actions/run.py — The `run` action.

This is the entry point for actually executing a workflow. It receives the
`type` parameter and dispatches into TYPE_DISPATCH via the second-level
registry.

Two-level dispatch:
  workflow(action="run", type="research", ...)  →  THIS handler  →  TYPE_DISPATCH["research"]

Each type handler validates its specific params and calls _execute_workflow()
to invoke workflows.base.run_workflow.

[DESIGN] The `run` action is intentionally thin — it does NOT perform
workflow-specific validation (target_file, project_root, etc.). That
validation lives in the type handler so it's co-located with the type's
other logic. The run action only validates that `type` is non-empty and
registered.

[DESIGN] **kwargs forwarding: the run action signature includes a fixed
list of well-known params (code, target_file, etc.) PLUS **kwargs. The
**kwargs catch-all lets list-valued params (e.g. `steps` for type="compose")
flow through without polluting the MCP schema — FastMCP doesn't handle
list-typed params well, so `steps` stays in **kwargs and the compose type
handler reads it from there.

[v1.2] Template support: when `template` is non-empty, the handler loads
the template via templates._registry.get_template(), uses the template's
`params` as the base, overrides with caller-supplied params (caller wins),
sets `type` from the template's `type` field (caller can't override `type`
when using a template — the template defines the type), validates all
`required` params are present, then forwards the merged params to the
type handler.
"""
from __future__ import annotations

from tools.workflow_ops._registry import register_action
from tools.workflow_ops._type_registry import TYPE_DISPATCH
from tools.workflow_ops.helpers import _ensure_trace_id, _make_error


@register_action(
    "workflow", "run",
    help_text="""run — Launch a multi-step autonomous workflow.
Required: type (research|data|autocode|deep_research|understand|autoresearch|auto|compose), goal
Optional: code (data), target_file/mode/error_msg/feature_desc/files/git_diff/dry_run (autocode),
          project_root (understand/autoresearch), trace_id, resume, timeout,
          steps (compose — list of step dicts, each {type, goal, ...}),
          template (v1.2 NEW — name of a template from templates/ subfolder; pre-sets type + params)
Returns: {status, workflow, trace_id, ...} (workflow-specific)""",
    examples=[
        'workflow(action="run", type="research", goal="Survey LLM agent frameworks")',
        'workflow(action="run", type="data", goal="Analyze sales.csv", code="print(df.head())")',
        'workflow(action="run", type="autocode", goal="Fix login bug", target_file="auth.py", mode="fix_error", error_msg="KeyError: user")',
        'workflow(action="run", type="understand", goal="Map codebase", project_root="/path/to/repo")',
        'workflow(action="run", type="auto", goal="Find recent papers on RAG")',
        'workflow(action="run", type="compose", goal="Survey + analyze", steps=[{"type":"research","goal":"Survey X"},{"type":"data","goal":"Analyze","code":"print(1)"}])',
        'workflow(action="run", template="bug-fix", target_file="auth.py", error_msg="KeyError: user")',
    ],
)
def _action_run(
    type: str = "",
    goal: str = "",
    # data workflow
    code: str = "",
    # autocode workflow
    target_file: str = "",
    mode: str = "improve",
    error_msg: str = "",
    feature_desc: str = "",
    files: str = "",
    git_diff: bool = False,
    dry_run: bool = False,
    # understand / autoresearch workflow
    project_root: str = "",
    # common
    trace_id: str = "",
    resume: bool = False,
    # per-workflow timeout (0 = use workflow default; autocode ignores this
    # and uses cfg.autocode_graph_timeout instead)
    timeout: int = 0,
    # [v3.4 #38] HiTL approval flag — set to True when resuming after human approval
    hitl_approved: bool = False,
    # [v1.2] Template name — when set, loads pre-set params from
    # templates/<name>.json. Caller params override template params.
    template: str = "",
    **kwargs,
) -> dict:
    """Run a workflow of the given type.

    Validates `type` is non-empty and registered in TYPE_DISPATCH, then
    forwards all parameters to the type handler. The type handler is
    responsible for type-specific validation and calling _execute_workflow().

    [v1.2] When `template` is non-empty, loads the template's params, merges
    with caller params (caller wins), sets `type` from the template, validates
    `required` params are present, then forwards to the type handler.
    """
    # ── v1.2: Template path ─────────────────────────────────────────────
    # When template is non-empty, load it, merge params (caller wins), set
    # type from template (caller can't override), validate required params,
    # then forward to the type handler with merged params.
    if template and template.strip():
        from tools.workflow_ops.templates._registry import (
            get_template, TEMPLATES,
        )

        tmpl = get_template(template.strip())
        if tmpl is None:
            return _make_error(
                f"Template not found: {template}",
                trace_id,
                available_templates=sorted(TEMPLATES.keys()),
            )

        # The template defines the workflow type — caller can't override it.
        # (If caller passes both type + template, template wins.)
        type = tmpl.get("type", "")

        # Build merged params: start with template's pre-set params, then
        # override with caller-supplied params (caller wins).
        tmpl_params = dict(tmpl.get("params", {}))
        # Resolve template param defaults that reference caller params
        # (e.g. goal="Refactor {target_file} for clarity"). We do a simple
        # str.format-style substitution using caller-supplied values.
        caller_params = {
            "goal": goal,
            "code": code,
            "target_file": target_file,
            "mode": mode,
            "error_msg": error_msg,
            "feature_desc": feature_desc,
            "files": files,
            "git_diff": git_diff,
            "dry_run": dry_run,
            "project_root": project_root,
        }
        # Apply caller overrides on top of template params. Caller wins
        # for any param the caller explicitly set (non-empty / non-default).
        # We treat the empty string / False / "improve" (mode default) as
        # "not set by caller" for the override check. This is conservative:
        # if the caller passes mode="" (which would be unusual), the
        # template's mode wins.
        merged = dict(tmpl_params)
        for k, v in caller_params.items():
            if k == "mode":
                # mode default is "improve" — only override if caller
                # explicitly set a non-default mode.
                if v and v != "improve":
                    merged[k] = v
            elif isinstance(v, bool):
                if v:  # only override if True (default is False)
                    merged[k] = v
            elif v:  # non-empty string
                merged[k] = v

        # Resolve {placeholder} references in string values using the
        # final merged params (e.g. goal="Refactor {target_file} ...").
        # Best-effort — if substitution fails (missing key), leave the
        # original string with the placeholder intact.
        for k, v in list(merged.items()):
            if isinstance(v, str) and "{" in v:
                try:
                    merged[k] = v.format(**merged)
                except (KeyError, IndexError, ValueError):
                    pass

        # Validate required params are present in the merged dict.
        required = tmpl.get("required", []) or []
        missing = [
            r for r in required
            if not merged.get(r)
            or (isinstance(merged.get(r), str) and not merged.get(r).strip())
        ]
        if missing:
            return _make_error(
                f"Template '{template}' requires params that are missing or "
                f"empty: {missing}. Either pass them as caller params or "
                f"add them to the template's 'params' field.",
                trace_id,
                template=template,
                required=required,
                missing=missing,
            )

        # Forward the merged params + control params to the type handler.
        # We extract the well-known params from `merged` so the type
        # handler's signature is satisfied; everything else flows through
        # **kwargs.
        trace_id = _ensure_trace_id(trace_id, merged.get("goal", ""))

        if type not in TYPE_DISPATCH:
            return _make_error(
                f"Template '{template}' specifies workflow type '{type}' "
                f"which is not registered in TYPE_DISPATCH. Valid: "
                f"{sorted(TYPE_DISPATCH.keys())}",
                trace_id,
                valid_types=sorted(TYPE_DISPATCH.keys()),
            )

        type_handler = TYPE_DISPATCH[type]["func"]
        # Build the kwargs dict for the type handler. The well-known params
        # are pulled from merged; control params (trace_id, resume, timeout,
        # hitl_approved) come from the caller's original kwargs.
        handler_kwargs = {
            "goal": merged.get("goal", ""),
            "code": merged.get("code", ""),
            "target_file": merged.get("target_file", ""),
            "mode": merged.get("mode", "improve"),
            "error_msg": merged.get("error_msg", ""),
            "feature_desc": merged.get("feature_desc", ""),
            "files": merged.get("files", ""),
            "git_diff": bool(merged.get("git_diff", False)),
            "dry_run": bool(merged.get("dry_run", False)),
            "project_root": merged.get("project_root", ""),
            "trace_id": trace_id,
            "resume": resume,
            "timeout": timeout,
            "hitl_approved": hitl_approved,
        }
        # Carry through any other template-supplied params (e.g.
        # skip_embeddings for understand) via **kwargs.
        reserved = set(handler_kwargs.keys()) | {"type", "template"}
        for k, v in merged.items():
            if k not in reserved:
                handler_kwargs[k] = v
        # Also pass through any caller **kwargs that aren't already covered.
        for k, v in kwargs.items():
            if k not in handler_kwargs:
                handler_kwargs[k] = v

        return type_handler(**handler_kwargs)

    # ── Standard (non-template) path ────────────────────────────────────
    trace_id = _ensure_trace_id(trace_id, goal)

    if not type or not type.strip():
        return _make_error(
            "type is required for action='run'",
            trace_id,
            valid_types=sorted(TYPE_DISPATCH.keys()),
        )

    wf_type = type.strip().lower()

    if wf_type not in TYPE_DISPATCH:
        return _make_error(
            f"Invalid workflow type '{type}'. Valid: {sorted(TYPE_DISPATCH.keys())}",
            trace_id,
            valid_types=sorted(TYPE_DISPATCH.keys()),
        )

    type_handler = TYPE_DISPATCH[wf_type]["func"]
    return type_handler(
        goal=goal,
        code=code,
        target_file=target_file,
        mode=mode,
        error_msg=error_msg,
        feature_desc=feature_desc,
        files=files,
        git_diff=git_diff,
        dry_run=dry_run,
        project_root=project_root,
        trace_id=trace_id,
        resume=resume,
        timeout=timeout,
        hitl_approved=hitl_approved,
        **kwargs,
    )
