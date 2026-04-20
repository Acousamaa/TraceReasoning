import requests
import json
import pandas as pd
import time
import os
import re
from typing import Optional, Dict

# === 1. 配置与路径 ===
API_URL = "http://XXXXXXXXX/api/chat"
MODEL_NAME = "XXXXXXXX"  # 

# 知识库路径映射
KB_PATHS = {
    "software": "/Knowledge_enhancement/software_2_group.csv",
    "tactics": "/Knowledge_enhancement/tactics_knowledge.csv",
    "techniques": "/Knowledge_enhancement/techniques_knowledge.csv",
    "cves": "/Knowledge_enhancement/cves_knowledge.csv",
    "ip_domain": "/Knowledge_enhancement/IP_domain_knowledge_cache.csv"
}

# === 2. 加载全量知识库 ===
def load_all_knowledge() -> Dict[str, Optional[pd.DataFrame]]:
    """加载所有维度的 CSV 知识库文件"""
    kb_data = {}
    for key, path in KB_PATHS.items():
        if os.path.exists(path):
            kb_data[key] = pd.read_csv(path)
        else:
            print(f"⚠️ 知识库文件未找到: {path}")
            kb_data[key] = None
    return kb_data

# === 3. 多维度自适应检索逻辑===
def get_dynamic_knowledge(report_text: str, kb_dict: Dict[str, pd.DataFrame]) -> str:
    knowledge_entries = []

    # --- (1) 恶意软件 (Malware) ---
    sw_df = kb_dict.get("software")
    if sw_df is not None:
        for _, row in sw_df.iterrows():
            software = str(row['software name']).strip()
            group = str(row['group name']).strip()
            pattern = re.compile(rf'\b{re.escape(software)}\b', re.IGNORECASE)
            if pattern.search(report_text):
                is_exclusive = 'exclusivity' in row and str(row['exclusivity']).lower() == 'high'
                desc = "dedicated/exclusive tool" if is_exclusive else "associated tool"
                knowledge_entries.append(f"[Malware] The tool '{software}' is a known {desc} of the threat actor {group}.")

    # --- (2) 战术 (Tactics) ---
    tac_df = kb_dict.get("tactics")
    if tac_df is not None:
        for _, row in tac_df.iterrows():
            ta_id = str(row.get('ta-ID', '')).strip()
            description = str(row.get('description', '')).strip()
            if ta_id and description and description.lower() != 'nan':
                if re.search(rf'\b{re.escape(ta_id)}\b', report_text):
                    knowledge_entries.append(f"[Tactic] {ta_id}: {description}")

    # --- (3) 技术 (Techniques) ---
    tech_df = kb_dict.get("techniques")
    if tech_df is not None:
        for _, row in tech_df.iterrows():
            tech_id = str(row.get('tech-ID', '')).strip()
            description = str(row.get('description', '')).strip()
            if tech_id and description and description.lower() != 'nan':
                if re.search(rf'\b{re.escape(tech_id)}\b', report_text):
                    knowledge_entries.append(f"[Technique] {tech_id}: {description}")

    # --- (4) 漏洞 (CVEs) ---
    cve_df = kb_dict.get("cves")
    if cve_df is not None:
        for _, row in cve_df.iterrows():
            cve_id = str(row.get('cve_id', '')).strip()
            description = str(row.get('descriptions', '')).strip()
            if cve_id and description and description.lower() != 'nan':
                if re.search(rf'\b{re.escape(cve_id)}\b', report_text, re.IGNORECASE):
                    knowledge_entries.append(f"[Vulnerability] {cve_id}: {description}")

    # --- (5) IP & Domain ---
    ip_dom_df = kb_dict.get("ip_domain")
    if ip_dom_df is not None:
        if 'IP' in ip_dom_df.columns and 'geolocation' in ip_dom_df.columns:
            for _, row in ip_dom_df.iterrows():
                ip_addr = str(row['IP']).strip()
                geo = str(row.get('geolocation', '')).strip()
                if ip_addr and geo and geo.lower() != 'nan' and ip_addr in report_text:
                    knowledge_entries.append(f"[Infrastructure] IP {ip_addr} is located in {geo}.")
        
        if 'domain' in ip_dom_df.columns and 'malicious category' in ip_dom_df.columns:
            for _, row in ip_dom_df.iterrows():
                domain = str(row['domain']).strip()
                category = str(row.get('malicious category', '')).strip()
                if domain and category and category.lower() != 'nan' and domain.lower() in report_text.lower():
                    knowledge_entries.append(f"[Infrastructure] Domain '{domain}' is categorized as: {category}.")

    if not knowledge_entries:
        return "# External Knowledge Base: No specific domain knowledge matches identified."

    header = "### EXTERNAL KNOWLEDGE ENHANCEMENT (Contextual Intelligence) ###\n"
    content = "\n".join([f"- {entry}" for entry in knowledge_entries])
    footer = "\n##############################################################"
    return header + content + footer

# === 4. 提示词模板 ===
prompt_template = """
You are a Senior Threat Intelligence Analyst specializing in APT attribution. Your task is to analyze a threat intelligence report (where the actor's name is masked) and reason step-by-step using the Diamond Model.

# Chain-of-Thought (CoT) Instructions
Please follow this 3-phase reasoning process strictly. Do not jump to the conclusion.

## Phase 1: Strategic Intent & Victim Profiling (Victim)
1. **Victim Analysis**: Who is being targeted? (Sector, Region, Tech Stack).
2. **Intent Analysis**: Is the goal Espionage, Sabotage, or Financial gain?

## Phase 2: Technical Artifact Enrichment (Capability & Infrastructure)
1. **TTP & Software Alignment**: Identify techniques and malware families.
2. **Knowledge Integration**: You MUST utilize the "External Knowledge Base" provided below to verify if the technical artifacts (Malware, CVEs, Infrastructure) are linked to a known actor.

## Phase 3: Diamond Model Synthesis & Attribution
Synthesize all evidence into the Diamond Model. Provide a final verdict. High-confidence indicators from the Knowledge Base must carry the highest weight.

# Input Data
{DYNAMIC_KNOWLEDGE}

Report Context:
{THREAT_REPORT}

# Output Format
Please output the Result first, then output your detailed reasoning for each phase.
"""

# === 5. API 调用处理 ===
def test_api_connection() -> bool:
    payload = {"model": MODEL_NAME, "messages": [{"role": "user", "content": "test"}], "stream": False}
    try:
        response = requests.post(API_URL, json=payload, timeout=20)
        return response.status_code == 200
    except:
        return False

def get_single_prediction(formatted_prompt: str) -> str:
    max_attempts = 6
    attempts = 0
    while attempts < max_attempts:
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": "You are a cybersecurity expert specializing in threat intelligence attribution."},
                {"role": "user", "content": formatted_prompt}
            ],
            "stream": True,
            "options": {"temperature": 0.6, "num_ctx": 16384}
        }
        try:
            full_response = ""
            with requests.post(API_URL, json=payload, stream=True, timeout=300) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if 'message' in data and 'content' in data['message']:
                            full_response += data['message']['content']
                        if data.get('done'):
                            break
            
            if len(full_response.strip()) > 50:
                return full_response
                
            attempts += 1
            print(f"⚠️ 响应过短，重试 {attempts}/{max_attempts}")
        except Exception as e:
            print(f"⚠️ API 调用异常 (尝试 {attempts+1}): {e}")
            attempts += 1
            time.sleep(1)
    return "Max retries exceeded"

def format_taa(text: str) -> str:
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    return cleaned

# === 6. 主循环逻辑 ===
def run_taa_task(input_file: str, output_csv: str, min_len: int = 100):
    if not test_api_connection():
        print(f"❌ 无法连接 API (模型: {MODEL_NAME})")
        return

    kb_dict = load_all_knowledge()
    df_in = pd.read_csv(input_file)
    real_group_col = df_in.columns[0]

    if os.path.exists(output_csv):
        df_out = pd.read_csv(output_csv)
    else:
        df_out = df_in[[real_group_col]].copy()
        df_out['prediction'] = ""

    for idx, row in df_in.iterrows():
        if idx < len(df_out) and len(str(df_out.at[idx, 'prediction'])) > min_len:
            continue

        content = str(row['content'])
        
        # 步骤 1: 动态检索 6 个维度的知识
        dynamic_kb = get_dynamic_knowledge(content, kb_dict)
        
        # 打印当前行检索到的所有增强信息
        print(f"\n" + "="*60)
        print(f" [Row {idx+1}] 动态知识增强内容详情:")
        print("="*60)
        print(dynamic_kb)
        print("="*60 + "\n")

        # 步骤 2: 填充模板
        final_prompt = prompt_template.format(
            DYNAMIC_KNOWLEDGE=dynamic_kb,
            THREAT_REPORT=content
        )

        print(f"正在通过 模型 推理 Row {idx+1}...")
        raw_output = get_single_prediction(final_prompt)
        clean_output = format_taa(raw_output)

        # 步骤 3: 实时保存结果
        df_out.at[idx, 'prediction'] = clean_output
        df_out[[real_group_col, 'prediction']].to_csv(output_csv, index=False, encoding='utf-8')
        print(f"✅ Row {idx+1} 推理已完成并实时存盘。")


if __name__ == "__main__":
    run_taa_task(
        input_file="data/dataset.csv",
        output_csv="result/result.csv"
    )
