import pandas as pd
import re
from collections import defaultdict

# =========================
# 输入文件路径参数放最前面
# =========================
PRED_FILE = 'XXXXXXXX'
GROUP_FILE = 'XXXXXXX'


def normalize_text(text):
    """标准化文本：转小写，去除非字母数字字符（保留空格）"""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', str(text).lower()).strip()


def parse_aliases(alias_str):
    """从逗号分隔字符串中提取别名列表，并标准化"""
    if pd.isna(alias_str):
        return []
    aliases = [a.strip() for a in str(alias_str).split(',')]
    return [normalize_text(a) for a in aliases if a]


def extract_organizations_from_response(response_norm, all_org_aliases_map, org_name_to_id):
    """
    从模型响应中提取组织名称
    
    参数:
        response_norm: 标准化的模型响应文本
        all_org_aliases_map: 从别名到组织ID的映射
        org_name_to_id: 从标准化组织名到组织ID的映射
    
    返回:
        set: 提取到的组织ID集合
    """
    found_orgs = set()
    
    # 首先检查完整组织名称
    for org_norm, org_id in org_name_to_id.items():
        if org_norm and org_norm in response_norm:
            # 使用正则表达式确保是完整的单词
            pattern = r'\b' + re.escape(org_norm) + r'\b'
            if re.search(pattern, response_norm):
                found_orgs.add(org_id)
    
    # 然后检查别名
    for alias, org_id in all_org_aliases_map.items():  # 修复：使用参数名 all_org_aliases_map
        if alias and alias in response_norm:
            # 使用正则表达式确保是完整的单词
            pattern = r'\b' + re.escape(alias) + r'\b'
            if re.search(pattern, response_norm):
                found_orgs.add(org_id)
    
    return found_orgs


def safe_div(a, b):
    """安全除法，避免除零错误"""
    return a / b if b != 0 else 0.0


def calculate_f1(precision, recall):
    """计算F1分数"""
    return safe_div(2 * precision * recall, precision + recall)


def main():
    df_pred = pd.read_csv(PRED_FILE, dtype=str)
    df_group = pd.read_csv(GROUP_FILE, dtype=str)

    # =========================
    # 构建组织名称和别名映射
    # =========================
    
    # 从group_name.csv中构建完整映射
    org_id_map = {}  # 组织ID -> 标准化组织名
    org_name_to_id = {}  # 标准化组织名 -> 组织ID
    org_aliases_map = {}  # 组织ID -> 别名列表(标准化)
    all_aliases_map = {}  # 标准化别名 -> 组织ID
    org_display_names = {}  # 组织ID -> 显示名称
    
    # 为每个组织分配唯一ID
    org_id_counter = 0
    
    for _, row in df_group.iterrows():
        raw_name = row.get('name', '')
        norm_name = normalize_text(raw_name)
        
        if not norm_name or norm_name in org_name_to_id:
            continue
        
        org_id = org_id_counter
        org_id_counter += 1
        
        org_id_map[org_id] = norm_name
        org_name_to_id[norm_name] = org_id
        org_display_names[org_id] = raw_name.strip() if pd.notna(raw_name) else norm_name
        
        # 解析别名
        aliases = parse_aliases(row.get('associated groups', ''))
        org_aliases_map[org_id] = aliases
        
        # 为每个别名建立映射到组织ID
        for alias in aliases:
            if alias and alias not in all_aliases_map:
                all_aliases_map[alias] = org_id
    
    # =========================
    # 处理预测数据，计算指标
    # =========================
    
    # 初始化统计
    total_samples = 0
    
    # 整体TP/FP/FN
    global_tp = 0
    global_fp = 0
    global_fn = 0
    
    # 按组织统计
    org_stats = defaultdict(lambda: {
        "tp": 0,  # True Positives
        "fp": 0,  # False Positives
        "fn": 0,  # False Negatives
        "total": 0,  # 该组织作为真实标签的总数
        "display_name": ""
    })
    
    # 记录所有出现过的组织ID
    seen_org_ids = set()
    
    # 首先处理预测数据，确保所有组织都在映射中
    for _, row in df_pred.iterrows():
        true_label_raw = str(row.get('group_name', '')).strip()
        
        if pd.isna(true_label_raw) or true_label_raw.lower() == 'nan' or true_label_raw == '':
            continue
        
        norm_true = normalize_text(true_label_raw)
        
        # 如果真实组织不在映射中，添加它
        if norm_true not in org_name_to_id:
            org_id = org_id_counter
            org_id_counter += 1
            
            org_id_map[org_id] = norm_true
            org_name_to_id[norm_true] = org_id
            org_aliases_map[org_id] = []
            org_display_names[org_id] = true_label_raw
    
    # 再次遍历，计算指标
    for _, row in df_pred.iterrows():
        true_label_raw = str(row.get('group_name', '')).strip()
        model_resp_raw = str(row.get('prediction', '')).strip()
        
        if pd.isna(true_label_raw) or true_label_raw.lower() == 'nan' or true_label_raw == '':
            continue
        
        total_samples += 1
        norm_true = normalize_text(true_label_raw)
        norm_resp = normalize_text(model_resp_raw)
        
        # 获取真实组织ID
        true_org_id = org_name_to_id[norm_true]
        seen_org_ids.add(true_org_id)
        
        # 为组织设置显示名称
        if not org_stats[true_org_id]["display_name"]:
            org_stats[true_org_id]["display_name"] = org_display_names.get(true_org_id, true_label_raw)
        
        org_stats[true_org_id]["total"] += 1
        
        # 从响应中提取组织
        predicted_org_ids = extract_organizations_from_response(
            norm_resp, all_aliases_map, org_name_to_id  # 传递 all_aliases_map
        )
        
        # 关键修改：针对归因任务的特殊FP计算逻辑
        # 假设归因任务是单标签分类，每个样本应该只有一个正确组织
        # 模型可能输出多个组织，但我们只关心是否包含真实组织
        
        if not predicted_org_ids:
            # 如果模型没有预测任何组织
            global_fn += 1
            org_stats[true_org_id]["fn"] += 1
        elif true_org_id in predicted_org_ids:
            # 模型预测包含真实组织
            global_tp += 1
            org_stats[true_org_id]["tp"] += 1
            
            # 对于归因任务，如果模型预测了多个组织但包含真实组织，
            # 我们可以考虑以下策略：
            # 1. 如果模型输出多个组织，但包含真实组织，不计算FP（最宽松）
            # 2. 如果模型输出多个组织，但包含真实组织，计算其他组织为FP（最严格）
            # 3. 折中：只计算超出一定数量的预测为FP
            
            # 这里采用折中方案：如果预测的组织数量超过2个，则计算额外的FP
            # 但每个样本最多只计算1个FP（因为这是单标签分类）
            if len(predicted_org_ids) > 2:
                global_fp += 1
                # 将这个FP分配给第一个非真实组织
                for pred_org_id in predicted_org_ids:
                    if pred_org_id != true_org_id:
                        org_stats[pred_org_id]["fp"] += 1
                        break
        else:
            # 模型预测了组织，但不包含真实组织
            global_fn += 1
            global_fp += 1  # 错误预测了一个组织
            
            org_stats[true_org_id]["fn"] += 1
            
            # 将这个FP分配给第一个预测的组织（错误的预测）
            if predicted_org_ids:
                first_pred_org_id = next(iter(predicted_org_ids))
                org_stats[first_pred_org_id]["fp"] += 1
    
    # =========================
    # 计算各项指标
    # =========================
    
    print("=" * 60)
    print("威胁情报归因评估结果（单标签分类评估）")
    print("=" * 60)
    print(f"总样本数: {total_samples}")
    
    if total_samples == 0:
        print("无有效样本")
        return
    
    # 计算整体准确率（命中率）
    hit_accuracy = safe_div(global_tp, total_samples)
    
    # 计算Precision, Recall, F1
    precision = safe_div(global_tp, global_tp + global_fp)
    recall = safe_div(global_tp, global_tp + global_fn)
    f1 = calculate_f1(precision, recall)
    
    print(f"\n整体指标:")
    print(f"命中率(Hit Accuracy): {hit_accuracy:.4f} ({global_tp}/{total_samples})")
    print(f"Precision: {precision:.4f} (TP={global_tp}, FP={global_fp})")
    print(f"Recall: {recall:.4f} (TP={global_tp}, FN={global_fn})")
    print(f"F1-Score: {f1:.4f}")
    
    # 计算各组织指标
    print("\n各组织详细指标:")
    print("-" * 100)
    print(f"{'组织名称':<30} | {'TP':>4} | {'FP':>4} | {'FN':>4} | {'Precision':>9} | {'Recall':>9} | {'F1':>9} | {'样本数':>6}")
    print("-" * 100)
    
    # 只显示有样本的组织
    macro_precisions = []
    macro_recalls = []
    macro_f1s = []
    
    for org_id in sorted(seen_org_ids):
        stats = org_stats[org_id]
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]
        total = stats["total"]
        display_name = stats["display_name"]
        
        # 计算该组织的指标
        org_precision = safe_div(tp, tp + fp)
        org_recall = safe_div(tp, tp + fn)
        org_f1 = calculate_f1(org_precision, org_recall)
        
        # 添加到macro计算
        macro_precisions.append(org_precision)
        macro_recalls.append(org_recall)
        macro_f1s.append(org_f1)
        
        print(f"{display_name:<30} | {tp:4d} | {fp:4d} | {fn:4d} | "
              f"{org_precision:9.4f} | {org_recall:9.4f} | {org_f1:9.4f} | {total:6d}")
    
    # =========================
    # 计算宏观(Macro)和微观(Micro)指标
    # =========================
    
    # Macro平均（简单平均）
    macro_precision = safe_div(sum(macro_precisions), len(macro_precisions)) if macro_precisions else 0
    macro_recall = safe_div(sum(macro_recalls), len(macro_recalls)) if macro_recalls else 0
    macro_f1 = calculate_f1(macro_precision, macro_recall)
    
    # Micro平均（基于总TP/FP/FN）
    micro_precision = precision  # 与整体Precision相同
    micro_recall = recall  # 与整体Recall相同
    micro_f1 = calculate_f1(micro_precision, micro_recall)
    
    # Weighted平均（按样本数加权）
    weighted_precision_sum = 0
    weighted_recall_sum = 0
    weighted_f1_sum = 0
    total_weight = 0
    
    for org_id in seen_org_ids:
        stats = org_stats[org_id]
        weight = stats["total"]
        
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]
        
        org_precision = safe_div(tp, tp + fp)
        org_recall = safe_div(tp, tp + fn)
        org_f1 = calculate_f1(org_precision, org_recall)
        
        weighted_precision_sum += org_precision * weight
        weighted_recall_sum += org_recall * weight
        weighted_f1_sum += org_f1 * weight
        total_weight += weight
    
    weighted_precision = safe_div(weighted_precision_sum, total_weight)
    weighted_recall = safe_div(weighted_recall_sum, total_weight)
    weighted_f1 = calculate_f1(weighted_precision, weighted_recall)
    
    print("\n" + "=" * 60)
    print("汇总指标 (不同平均方式)")
    print("=" * 60)
    print(f"Macro平均    | Precision: {macro_precision:.4f} | Recall: {macro_recall:.4f} | F1: {macro_f1:.4f}")
    print(f"Micro平均    | Precision: {micro_precision:.4f} | Recall: {micro_recall:.4f} | F1: {micro_f1:.4f}")
    print(f"Weighted平均 | Precision: {weighted_precision:.4f} | Recall: {weighted_recall:.4f} | F1: {weighted_f1:.4f}")
    
    print("\nFP计算说明:")
    print("1. 每个样本最多计算1个FP（单标签分类假设）")
    print("2. 如果模型预测包含真实组织，且预测的组织数≤2，不计算FP")
    print("3. 如果模型预测包含真实组织，但预测的组织数>2，计算1个FP")
    print("4. 如果模型预测不包含真实组织，计算1个FP")
    print("=" * 60)


if __name__ == "__main__":
    main()