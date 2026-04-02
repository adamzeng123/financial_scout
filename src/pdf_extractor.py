"""
财报侦察官 - PDF提取模块
将年报PDF转为结构化financial_data.json和audit_opinion.txt。
流程：pymupdf提取文本 → 关键词定位报表页 → LLM提取数据 → 校验输出
"""

import json
import os
import re
from pathlib import Path
from openai import OpenAI
import fitz  # pymupdf

MODEL = "gpt-4o-mini"

# 需要提取的字段清单（用于校验）—— 这些是field_key，和ontology保持一致
REQUIRED_BS_FIELDS = [
    "货币资金", "应收账款", "存货", "流动资产合计", "资产总计",
    "短期借款", "应付票据", "交易性金融负债", "一年内到期的非流动负债",
    "流动负债合计", "负债合计", "归属于母公司所有者权益合计"
]

REQUIRED_IS_FIELDS = [
    "营业收入", "营业成本", "销售费用", "管理费用", "研发费用",
    "财务费用", "其中_利息费用", "利润总额", "所得税费用",
    "净利润", "归属于母公司股东的净利润"
]

REQUIRED_CF_FIELDS = [
    "经营活动产生的现金流量净额",
    "购建固定资产_无形资产和其他长期资产支付的现金"
]


def _load_ontology_aliases() -> str:
    """
    从ontology加载别名映射，格式化为LLM prompt中的术语参考段落。
    如果ontology不可用，返回空字符串（不影响提取流程）。
    """
    try:
        import ontology_service
        aliases_map = ontology_service.get_aliases_for_extraction()
        if not aliases_map:
            return ""
        lines = ["以下是各字段的别名对照表，年报中可能使用不同的名称，请统一映射到左侧的标准字段名："]
        for field_key, aliases in aliases_map.items():
            alt = [a for a in aliases if a != field_key]
            if alt:
                lines.append(f"  - {field_key} ← 也可能叫：{', '.join(alt)}")
        return "\n".join(lines)
    except Exception:
        return ""


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("请设置环境变量 OPENAI_API_KEY")
    return OpenAI(api_key=api_key)


# ---------------------------------------------------------------------------
# 1. PDF转文本
# ---------------------------------------------------------------------------

def pdf_to_text(pdf_path: str | Path) -> list[dict]:
    """
    将PDF每页转为文本，返回 [{"page": 1, "text": "..."}, ...]
    """
    doc = fitz.open(str(pdf_path))
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text()
        pages.append({"page": i + 1, "text": text})
    doc.close()
    return pages


# ---------------------------------------------------------------------------
# 2. 关键词定位报表页面
# ---------------------------------------------------------------------------

def find_pages_by_keywords(pages: list[dict], keywords: list[str],
                           context_pages: int = 3) -> str:
    """
    搜索包含关键词的页面，返回这些页面及其前后context_pages页的合并文本。
    """
    matched_indices = set()
    for i, page in enumerate(pages):
        for kw in keywords:
            if kw in page["text"]:
                for offset in range(-1, context_pages + 1):
                    idx = i + offset
                    if 0 <= idx < len(pages):
                        matched_indices.add(idx)

    if not matched_indices:
        return ""

    sorted_indices = sorted(matched_indices)
    sections = []
    for idx in sorted_indices:
        sections.append(f"=== 第{pages[idx]['page']}页 ===\n{pages[idx]['text']}")

    return "\n\n".join(sections)


def find_financial_statements(pages: list[dict]) -> dict[str, str]:
    """
    定位三张主要报表和审计意见的文本段落。
    """
    return {
        "balance_sheet": find_pages_by_keywords(
            pages, ["合并资产负债表", "合并及母公司资产负债表"], context_pages=3
        ),
        "income_statement": find_pages_by_keywords(
            pages, ["合并利润表", "合并及母公司利润表"], context_pages=2
        ),
        "cash_flow": find_pages_by_keywords(
            pages, ["合并现金流量表", "合并及母公司现金流量表"], context_pages=2
        ),
        "audit_opinion": find_pages_by_keywords(
            pages, ["审计意见类型", "审计报告", "审计意见"], context_pages=3
        ),
    }


# ---------------------------------------------------------------------------
# 3. LLM提取结构化数据
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """你是专业的财务数据提取员。请从以下年报文本中提取合并报表的财务数据。

要求：
- 提取本期（当年）和上期（上年）两列数据
- 直接提取原文中的数字，不要做单位换算（系统会自动处理单位）
- 严格以JSON格式返回，不要返回其他内容
- 如果某个字段在文本中找不到，值设为null
- 注意区分合并报表和母公司报表，只提取合并报表数据

返回格式：
{{
  "current_period": {{
    "balance_sheet": {{
      "货币资金": 数字,
      "应收账款": 数字,
      "存货": 数字,
      "流动资产合计": 数字,
      "资产总计": 数字,
      "短期借款": 数字,
      "应付票据": 数字,
      "交易性金融负债": 数字,
      "一年内到期的非流动负债": 数字,
      "流动负债合计": 数字,
      "负债合计": 数字,
      "归属于母公司所有者权益合计": 数字
    }},
    "income_statement": {{
      "营业收入": 数字,
      "营业成本": 数字,
      "销售费用": 数字,
      "管理费用": 数字,
      "研发费用": 数字,
      "财务费用": 数字,
      "其中_利息费用": 数字,
      "利润总额": 数字,
      "所得税费用": 数字,
      "净利润": 数字,
      "归属于母公司股东的净利润": 数字
    }},
    "cash_flow": {{
      "经营活动产生的现金流量净额": 数字,
      "购建固定资产_无形资产和其他长期资产支付的现金": 数字
    }}
  }},
  "prior_period": {{
    (同上结构)
  }}
}}

以下是年报文本：

【资产负债表】
{balance_sheet_text}

【利润表】
{income_statement_text}

【现金流量表】
{cash_flow_text}"""


UNIT_MAP = {
    "元": 1,
    "千元": 1_000,
    "万元": 10_000,
    "百万元": 1_000_000,
    "亿元": 100_000_000,
    # 英文
    "yuan": 1,
    "thousands": 1_000,
    "thousands of rmb": 1_000,
    "ten thousands": 10_000,
    "millions": 1_000_000,
    "millions of rmb": 1_000_000,
    # 港币
    "千港元": 1_000,
    "百万港元": 1_000_000,
    # 繁体
    "千元（人民幣）": 1_000,
}

UNIT_DETECT_PROMPT = """请从以下财务报表文本中识别金额的计量单位。

只需要返回一个JSON：
{{"unit": "元 或 千元 或 万元 或 百万元 或 亿元", "confidence": "high 或 medium 或 low", "evidence": "你在文本中找到的原文依据"}}

注意：
- 寻找"单位"、"金额单位"、"币种"、"Unit"等关键词附近的描述
- 常见表述："单位为：千元"、"（金额单位为人民币千元）"、"in thousands of RMB"
- 如果文本中有多种单位描述，以合并报表的为准
- 如果完全找不到，根据数字的量级推断（如果营业收入是几十万到几百万，很可能是千元或万元单位）
- 只返回JSON，不要返回其他内容

以下是报表文本的开头部分：
{text}"""


def detect_unit(sections: dict[str, str]) -> tuple[str, float, str]:
    """
    从报表文本中检测金额单位。
    策略：LLM识别 → 映射到乘数。
    返回 (单位名称, 换算到元的乘数, 置信度)。
    """
    # 取每张报表的前1500字符，一般单位声明在报表开头
    texts = []
    for key in ["balance_sheet", "income_statement", "cash_flow"]:
        t = sections.get(key, "")
        if t:
            texts.append(t[:1500])
    combined = "\n".join(texts)

    if not combined.strip():
        return "元", 1, "low"

    client = get_client()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=200,
            temperature=0,
            messages=[{
                "role": "user",
                "content": UNIT_DETECT_PROMPT.format(text=combined[:4000])
            }]
        )
        raw = response.choices[0].message.content.strip()

        # 解析JSON
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0]
        result = json.loads(cleaned.strip())

        unit_str = result.get("unit", "元").strip()
        confidence = result.get("confidence", "medium")
        evidence = result.get("evidence", "")

        # 映射到乘数
        multiplier = UNIT_MAP.get(unit_str, None)
        if multiplier is None:
            # 模糊匹配
            unit_lower = unit_str.lower().replace(" ", "")
            for key, val in UNIT_MAP.items():
                if key.lower().replace(" ", "") in unit_lower or unit_lower in key.lower().replace(" ", ""):
                    multiplier = val
                    break
            if multiplier is None:
                multiplier = 1
                confidence = "low"

        return unit_str, multiplier, confidence

    except Exception:
        # LLM失败，兜底返回元
        return "元（LLM检测失败）", 1, "low"


def _apply_unit_multiplier(data: dict, multiplier: float) -> dict:
    """将所有财务数值乘以单位换算系数。"""
    if multiplier == 1:
        return data

    for period_key in ["current_period", "prior_period"]:
        period = data.get(period_key, {})
        for table_key in ["balance_sheet", "income_statement", "cash_flow"]:
            table = period.get(table_key, {})
            for field_key, value in table.items():
                if value is not None and isinstance(value, (int, float)):
                    table[field_key] = value * multiplier

    return data


def extract_financial_data(sections: dict[str, str], company: str,
                           report_year: int) -> dict:
    """
    调用LLM从报表文本中提取结构化财务数据。

    策略：
    - 将三张报表文本一起发送（减少调用次数）
    - 如果文本过长（>15000字符），分开发送
    - 校验返回的JSON是否包含所有必要字段
    """
    client = get_client()

    # 自动检测报表单位（LLM识别）
    detected_unit, multiplier, unit_confidence = detect_unit(sections)

    bs_text = sections["balance_sheet"][:8000]
    is_text = sections["income_statement"][:5000]
    cf_text = sections["cash_flow"][:5000]

    # 从ontology注入术语别名，提高跨公司/跨语言提取容错
    aliases_ref = _load_ontology_aliases()
    prompt = EXTRACT_PROMPT.format(
        balance_sheet_text=bs_text or "（未找到资产负债表文本）",
        income_statement_text=is_text or "（未找到利润表文本）",
        cash_flow_text=cf_text or "（未找到现金流量表文本）"
    )
    if aliases_ref:
        prompt = prompt + "\n\n" + aliases_ref

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=3000,
            temperature=0,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        raw = response.choices[0].message.content.strip()

        # 剥离可能的markdown代码块
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            cleaned = cleaned.rsplit("```", 1)[0]

        data = json.loads(cleaned.strip())

        # 包装为完整格式
        result = {
            "company": company,
            "report_year": report_year,
            "currency": "RMB",
            "unit": "元",
            "detected_unit": detected_unit,
            "unit_multiplier": multiplier,
            "unit_confidence": unit_confidence,
            "current_period": {
                "label": f"{report_year}年度",
                **data.get("current_period", {})
            },
            "prior_period": {
                "label": f"{report_year - 1}年度",
                **data.get("prior_period", {})
            }
        }

        # 自动换算单位到元
        if multiplier != 1:
            result = _apply_unit_multiplier(result, multiplier)

        return result

    except Exception as e:
        raise RuntimeError(f"LLM财务数据提取失败: {e}")


# ---------------------------------------------------------------------------
# 4. 审计意见提取
# ---------------------------------------------------------------------------

AUDIT_EXTRACT_PROMPT = """请从以下年报文本中提取完整的审计报告部分。

要求：
- 提取审计意见类型、审计机构、签署日期、审计意见正文、关键审计事项等全部内容
- 保持原文，不要修改或总结
- 只返回审计报告的文本内容，不要返回其他部分

年报文本：
{audit_text}"""


def extract_audit_opinion(sections: dict[str, str]) -> str:
    """
    调用LLM从PDF文本中提取完整的审计意见段落。
    """
    audit_text = sections.get("audit_opinion", "")

    if not audit_text:
        return "未找到审计意见段落"

    client = get_client()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=2000,
            temperature=0,
            messages=[{
                "role": "user",
                "content": AUDIT_EXTRACT_PROMPT.format(
                    audit_text=audit_text[:6000]
                )
            }]
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        # 回退：直接返回原始文本的前2000字符
        return audit_text[:2000]


# ---------------------------------------------------------------------------
# 5. 校验
# ---------------------------------------------------------------------------

def validate_financial_data(data: dict) -> list[str]:
    """
    校验提取的数据是否完整。返回缺失字段列表。
    """
    missing = []

    for period_key in ["current_period", "prior_period"]:
        period = data.get(period_key, {})
        label = period.get("label", period_key)

        bs = period.get("balance_sheet", {})
        for field in REQUIRED_BS_FIELDS:
            if bs.get(field) is None:
                missing.append(f"{label} 资产负债表.{field}")

        inc = period.get("income_statement", {})
        for field in REQUIRED_IS_FIELDS:
            if inc.get(field) is None:
                missing.append(f"{label} 利润表.{field}")

        cf = period.get("cash_flow", {})
        for field in REQUIRED_CF_FIELDS:
            if cf.get(field) is None:
                missing.append(f"{label} 现金流量表.{field}")

    return missing


# ---------------------------------------------------------------------------
# 6. 主流程：PDF → JSON + TXT
# ---------------------------------------------------------------------------

def process_pdf(pdf_path: str | Path, company: str, report_year: int,
                output_dir: str | Path | None = None) -> dict:
    """
    完整流程：PDF → 文本 → 定位 → LLM提取 → 校验 → 保存。

    返回：
    {
        "financial_data": dict,
        "audit_opinion": str,
        "missing_fields": list,
        "pages_found": dict  # 各报表找到的页码
    }
    """
    pdf_path = Path(pdf_path)
    if output_dir is None:
        output_dir = pdf_path.parent
    output_dir = Path(output_dir)

    # Step 1: PDF转文本
    pages = pdf_to_text(pdf_path)

    # Step 2: 定位报表页面
    sections = find_financial_statements(pages)

    # 记录找到的页码
    pages_found = {}
    for key, text in sections.items():
        page_nums = re.findall(r"=== 第(\d+)页 ===", text)
        pages_found[key] = [int(p) for p in page_nums]

    # Step 3: LLM提取财务数据
    financial_data = extract_financial_data(sections, company, report_year)

    # Step 4: LLM提取审计意见
    audit_opinion = extract_audit_opinion(sections)

    # Step 5: 校验
    missing = validate_financial_data(financial_data)

    # Step 6: 按公司+年度建子目录保存
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', company)
    sub_dir = output_dir / f"{safe_name}_{report_year}"
    sub_dir.mkdir(parents=True, exist_ok=True)

    json_path = sub_dir / "financial_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(financial_data, f, ensure_ascii=False, indent=2)

    txt_path = sub_dir / "audit_opinion.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(audit_opinion)

    # 返回数据集ID供前端引用
    dataset_id = f"{safe_name}_{report_year}"

    return {
        "financial_data": financial_data,
        "audit_opinion": audit_opinion,
        "missing_fields": missing,
        "pages_found": pages_found,
        "dataset_id": dataset_id,
        "output_json": str(json_path),
        "output_txt": str(txt_path),
    }


# ---------------------------------------------------------------------------
# 独立运行
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    if len(sys.argv) < 4:
        print("用法: python pdf_extractor.py <pdf路径> <公司名> <报告年度>")
        print("示例: python pdf_extractor.py ../立讯精密2024年.pdf 立讯精密工业股份有限公司 2024")
        sys.exit(1)

    pdf_path = sys.argv[1]
    company = sys.argv[2]
    report_year = int(sys.argv[3])

    print(f"正在处理: {pdf_path}")
    print(f"公司: {company}, 年度: {report_year}")
    print()

    result = process_pdf(pdf_path, company, report_year)

    fd = result["financial_data"]
    detected = fd.get("detected_unit", "元")
    mult = fd.get("unit_multiplier", 1)
    confidence = fd.get("unit_confidence", "unknown")
    print(f"检测到单位: {detected} (置信度: {confidence})" + (f" → 已自动换算 ×{mult:,.0f} 到元" if mult != 1 else ""))
    print(f"报表页码: {result['pages_found']}")
    print(f"输出JSON: {result['output_json']}")
    print(f"输出TXT:  {result['output_txt']}")

    # 抽样验证：显示几个关键数值供人工确认
    cur_is = fd.get("current_period", {}).get("income_statement", {})
    cur_bs = fd.get("current_period", {}).get("balance_sheet", {})
    rev = cur_is.get("营业收入")
    ta = cur_bs.get("资产总计")
    if rev is not None:
        print(f"营业收入: {rev/1e8:.2f}亿元")
    if ta is not None:
        print(f"资产总计: {ta/1e8:.2f}亿元")

    if result["missing_fields"]:
        print(f"\n警告：以下字段未提取到：")
        for f in result["missing_fields"]:
            print(f"  - {f}")
    else:
        print("\n所有字段提取完整。")
