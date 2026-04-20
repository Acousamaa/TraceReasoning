# TraceReasoning: Adaptive Knowledge Enhancement and Structured Chain-of-Thought Reasoning for Threat Actor Attribution

TraceReasoning is a knowledge-intensive reasoning framework designed for high-fidelity threat actor attribution. By integrating **Adaptive Domain Knowledge Enhancement (ADKE)** with a **Structured Chain-of-Thought (CoT)** backbone based on the Diamond Model, it effectively bridges the gap caused by attribute sparsity in raw Cyber Threat Intelligence (CTI) reports.

## 🚀 Key Features

- **Structured Cognitive Backbone**: Implements a constrained reasoning path based on the Diamond Model (Adversary, Capability, Infrastructure, Victim) to ensure logical consistency and prevent reasoning drift.
- **Adaptive Domain Knowledge Enhancement (ADKE)**: Automatically enriches sparse technical artifacts using a structured domain knowledge base ($\mathcal{KB}$) spanning Malware, Tactic, Technique, Vulnerability, IP, and Domain.
- **Heterogeneous Corpus**: Supports large-scale evaluation across 53 distinct threat actor categories with over 1,000 expert-verified forensic samples.
- **Multi-Model Support**: Evaluated across state-of-the-art LLM series, including **Qwen3** and **DeepSeek-R1**.

## 📁 Repository Structure

```text
TRACEREASONING/
├── datasets/                 # Integrated Forensic Corpus
│   ├── CTIBench/             # Open-source benchmark data
│   ├── from_ATT&CK/          # Real-world intelligence from ATT&CK portal
│   └── Guru/                 # Expert-curated attribution samples
├── cves.csv                  # Vulnerability (CVE) knowledge base
├── IP and Domain.csv         # Infrastructure (VT metadata) knowledge base
├── software_knowledge.csv    # Malware/Software analytical metadata
├── tactics_knowledge.csv     # Adversary tactics knowledge base
├── techniques_knowledge.csv  # Adversary techniques (TTPs) knowledge base
├── TraceReasoning.py         # Core framework implementation (ADKE + CoT)
├── evaluation.py             # Performance benchmarking & metrics script
└── README.md                 # Project documentation
```


