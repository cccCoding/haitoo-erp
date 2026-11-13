"""货盘每账号、每 SKU 的终身额度与整批容量分配。"""
import copy
import random
from collections import Counter, deque

from sqlalchemy import func, select

from .models import SupplyJob, SupplyJobMaterial
from .config import get_settings

SKU_USE_LIMIT = get_settings().sku_use_limit
QUOTA_VERSION = 1
INSUFFICIENT_MATERIALS = f"同一账号每个 SKU 累计最多使用 {SKU_USE_LIMIT} 次，当前筛选条件下剩余素材额度不足，请减少链接数量或补充素材"


def sku_use_counts(db, company_id, user_id, skus):
    """只统计已完成任务的最终商品链接；分页 IN 避免数据库参数数量限制。"""
    skus = list(dict.fromkeys(sku for sku in skus if sku))
    result = {}
    for offset in range(0, len(skus), 400):
        links = select(SupplyJobMaterial.sku, SupplyJobMaterial.job_id, SupplyJobMaterial.link_index).join(
            SupplyJob, SupplyJob.id == SupplyJobMaterial.job_id).where(
                SupplyJobMaterial.company_id == company_id, SupplyJob.company_id == company_id,
                SupplyJob.user_id == user_id, SupplyJob.state == "completed",
                SupplyJobMaterial.successful.is_(True), SupplyJobMaterial.link_index >= 0,
                SupplyJobMaterial.sku.in_(skus[offset:offset + 400])).distinct().subquery()
        result.update(db.execute(select(links.c.sku, func.count()).group_by(links.c.sku)).all())
    return result


def validate_link_quota(links, used):
    counts = Counter(item["sku"] for link in links for item in link["materials"])
    if any(used.get(sku, 0) + count > SKU_USE_LIMIT for sku, count in counts.items()):
        raise ValueError(INSUFFICIENT_MATERIALS)


def allocate_links(candidates, sku_count, link_count, seed, used, *, sample):
    """先按风格分配；贪心不够时用最大流验证并重排完整批次，不误报不足。"""
    budgets = {item["sku"]: max(0, SKU_USE_LIMIT - used.get(item["sku"], 0)) for item in candidates}
    if sum(budgets.values()) < sku_count * link_count:
        raise ValueError(INSUFFICIENT_MATERIALS)
    rng = random.Random(seed)
    remaining = budgets.copy()
    groups = []
    for _ in range(link_count):
        available = [item for item in candidates if remaining[item["sku"]] > 0]
        group = sample(available, sku_count, rng)
        if len(group) != sku_count:
            groups = _capacity_groups(candidates, budgets, sku_count, link_count, seed)
            break
        style = group[0].get("style_id")
        if style and all(item.get("style_id") == style for item in group):
            # 同风格内先用额度较多的 SKU，避免随机耗尽少数 SKU 后被迫混合风格。
            styled = [item for item in available if item.get("style_id") == style]
            levels = sorted({remaining[item["sku"]] for item in styled}, reverse=True)
            for level in levels[:-1]:
                pool = [item for item in styled if remaining[item["sku"]] >= level]
                if len(pool) >= sku_count:
                    balanced = sample(pool, sku_count, rng)
                    if len(balanced) == sku_count:
                        group = balanced
                        break
        groups.append(group)
        for item in group:
            remaining[item["sku"]] -= 1
    return [{"index": index, "materials": group, "title": None, "replaced": False}
            for index, group in enumerate(groups)]


def _capacity_groups(candidates, budgets, sku_count, link_count, seed):
    # 现有素材表保证 SKU 和 ID 唯一。源 -> SKU（剩余额度）-> 链接内 URL（去重）
    # -> 商品链接（指定 SKU 数量）-> 汇点，因此同时满足账号额度和链接内去重。
    candidates = [item for item in candidates if budgets[item["sku"]] > 0]
    if len({item["sku"] for item in candidates}) != len(candidates):
        raise ValueError("候选素材 SKU 重复")
    rng = random.Random(seed)
    rng.shuffle(candidates)
    graph = [[], []]
    source, sink = 0, 1

    def node():
        graph.append([])
        return len(graph) - 1

    def edge(start, end, capacity):
        forward = [end, capacity, len(graph[end])]
        graph[start].append(forward)
        graph[end].append([start, 0, len(graph[start]) - 1])
        return forward

    link_nodes = [node() for _ in range(link_count)]
    for target in link_nodes:
        edge(target, sink, sku_count)
    url_nodes, selections = {}, []
    for item in candidates:
        sku_node = node()
        edge(source, sku_node, min(budgets[item["sku"]], link_count))
        indices = list(range(link_count))
        rng.shuffle(indices)
        for index in indices:
            key = (index, item["url"])
            if key not in url_nodes:
                url_nodes[key] = node()
                edge(url_nodes[key], link_nodes[index], 1)
            selections.append((index, item, edge(sku_node, url_nodes[key], 1)))

    # Dinic；每次增广至少放入一个 SKU，总流量最多 9 × 50。
    total = 0
    while total < sku_count * link_count:
        levels = [-1] * len(graph)
        levels[source] = 0
        queue = deque([source])
        while queue:
            start = queue.popleft()
            for end, capacity, _ in graph[start]:
                if capacity and levels[end] < 0:
                    levels[end] = levels[start] + 1
                    queue.append(end)
        if levels[sink] < 0:
            raise ValueError(INSUFFICIENT_MATERIALS)
        positions = [0] * len(graph)

        def push(start, amount):
            if start == sink:
                return amount
            while positions[start] < len(graph[start]):
                current = graph[start][positions[start]]
                end, capacity, reverse = current
                if capacity and levels[end] == levels[start] + 1:
                    sent = push(end, min(amount, capacity))
                    if sent:
                        current[1] -= sent
                        graph[end][reverse][1] += sent
                        return sent
                positions[start] += 1
            return 0

        while sent := push(source, sku_count * link_count - total):
            total += sent
    groups = [[] for _ in range(link_count)]
    for index, item, selection in selections:
        if selection[1] == 0:
            groups[index].append(copy.deepcopy(item))
    return groups
