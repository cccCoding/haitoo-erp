"""本机模版策略校验和环境选择，不保存 ERP 或店铺凭据。"""
import random
from workbench import ERPRequestError


def validate_policy(payload, templates, environments, previous=None):
    if not isinstance(payload, dict) or type(payload.get("template_id")) is not int:
        raise ERPRequestError(400, "请选择有效模版")
    template = next((row for row in templates if row["id"] == payload["template_id"]), None)
    if not template:
        raise ERPRequestError(400, "模版不存在或无权访问")
    codes = payload.get("container_codes")
    mode = payload.get("mode", "round_robin")
    if mode not in ("round_robin", "random") or not isinstance(codes, list) or not codes or any(not isinstance(code, str) or not code for code in codes) or len(codes) != len(set(codes)):
        raise ERPRequestError(400, "请选择至少一个环境，且环境不能重复")
    allowed = {row["container_code"] for row in environments} | set((previous or {}).get("container_codes", []))
    if any(code not in allowed for code in codes):
        raise ERPRequestError(400, "不能添加本机不可访问的环境")
    return {"template_id": template["id"], "template_name": template["name"], "container_codes": codes, "mode": mode, "last_container_code": (previous or {}).get("last_container_code")}


def candidates(task, policies, environments, blocked=()):
    if task.get("template_id") is None:
        return [], "模版未知，请重新生成任务"
    policy = policies.get(str(task["template_id"]))
    if not policy:
        return [], "未配置策略"
    codes = policy["container_codes"]
    original = task.get("container_code")
    if original and original not in codes:
        return [], "原环境不在策略中"
    available = {row["container_code"]: row for row in environments if row["container_code"] not in blocked}
    if original:
        return ([available[original]], None) if original in available else ([], "无可用环境")
    ordered = list(codes)
    if policy.get("mode") == "random":
        random.shuffle(ordered)
    elif policy.get("last_container_code") in ordered:
        start = ordered.index(policy["last_container_code"]) + 1
        ordered = ordered[start:] + ordered[:start]
    choices = [available[code] for code in ordered if code in available]
    return choices, None if choices else "无可用环境"
