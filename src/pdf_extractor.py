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


def _load_ontology_context() -> str:
    """
    从ontology加载完整的提取语义上下文，包括：
    - 别名映射（跨语言/跨公司术语容错）
    - 提取提示（正负号、括号处理、子项关系）
    - 术语定义（帮助LLM理解含义以正确定位）

    如果ontology不可用，返回空字符串（不影响提取流程）。
    """
    try:
        import ontology_service
        data = ontology_service.load_current()
        terms = data.get("terms", {})
        if not terms:
            return ""

        # 按报表分组
        tables = {"balance_sheet": [], "income_statement": [], "cash_flow": []}
        for t in terms.values():
            table = t.get("source_table", "")
            if table in tables:
                tables[table].append(t)

        table_labels = {
            "balance_sheet": "资产负债表",
            "income_statement": "利润表",
            "cash_flow": "现金流量表",
        }

        lines = ["以下是术语语义参考，帮助你正确识别和提取每个字段：", ""]

        for table_key, table_terms in tables.items():
            if not table_terms:
                continue
            lines.append(f"【{table_labels[table_key]}字段】")
            for t in table_terms:
                field_key = t.get("field_key", t.get("canonical", ""))
                # 别名
                all_aliases = []
                for lang_aliases in t.get("aliases", {}).values():
                    all_aliases.extend(lang_aliases)
                alt = [a for a in dict.fromkeys(all_aliases) if a != field_key]
                alias_str = f"（别名：{', '.join(alt)}）" if alt else ""

                # 提取提示
                hint = t.get("extraction_hint", "")
                hint_str = f" → {hint}" if hint else ""

                # 子项关系
                parent = t.get("parent_item", "")
                parent_str = f" [是{parent}的子项]" if parent else ""

                lines.append(f"  - {field_key}{alias_str}{parent_str}{hint_str}")
            lines.append("")

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

def _is_data_page(text: str) -> bool:
    """判断页面是否包含实际财务数字（而不仅仅是目录引用）。"""
    numbers = re.findall(r'[\d,]{4,}', text)
    return len(numbers) >= 3


def _load_statement_keywords() -> dict[str, list[str]]:
    """
    从ontology加载各报表的搜索关键词。
    每个source_table的所有term的aliases都可以作为页面定位的线索。
    同时包含报表标题级别的关键词。
    """
    # 报表标题级关键词（用于书签和页面标题匹配）
    defaults = {
        "balance_sheet": [
            "合并资产负债表", "合并及母公司资产负债表", "合并及公司资产负债表",
            "合併資產負債表", "Consolidated Balance Sheet",
        ],
        "income_statement": [
            "合并利润表", "合并及母公司利润表", "合并及公司利润表",
            "合併損益表", "合併綜合損益表", "Consolidated Income Statement",
        ],
        "cash_flow": [
            "合并现金流量表", "合并及母公司现金流量表", "合并及公司现金流量表",
            "合併現金流量表", "Consolidated Cash Flow Statement",
        ],
        "audit_opinion": [
            "审计意见类型", "审计报告", "审计意见", "審計報告", "Audit Report",
        ],
    }

    # 从ontology补充：每张报表中的首个核心字段名作为数据锚点
    try:
        import ontology_service
        data = ontology_service.load_current()
        # 每张报表取前2个term的所有aliases作为数据锚点
        table_anchors = {"balance_sheet": [], "income_statement": [], "cash_flow": []}
        count = {"balance_sheet": 0, "income_statement": 0, "cash_flow": 0}
        for t in data.get("terms", {}).values():
            table = t.get("source_table", "")
            if table in table_anchors and count[table] < 2:
                for aliases in t.get("aliases", {}).values():
                    table_anchors[table].extend(aliases)
                count[table] += 1
        for table, anchors in table_anchors.items():
            if anchors:
                defaults[table] = defaults[table] + anchors
    except Exception:
        pass

    return defaults


def build_page_index(pdf_path: str | Path) -> dict:
    """
    构建PDF页面索引，三层策略定位报表页面：
    1. PDF书签（最可靠，大部分年报PDF都有结构化书签）
    2. LLM辅助（从目录页提取页码映射）
    3. 关键词扫描（ontology驱动，全页面扫描）

    返回 {"balance_sheet": page_num, "income_statement": page_num,
           "cash_flow": page_num, "audit_opinion": page_num,
           "method": "bookmark|llm_toc|keyword_scan"}
    """
    doc = fitz.open(str(pdf_path))
    toc = doc.get_toc()
    index = {}
    all_keywords = _load_statement_keywords()

    # 书签匹配只用报表标题级关键词（不用ontology term aliases）
    bookmark_keywords = {
        "balance_sheet": [
            "合并资产负债表", "合并及母公司资产负债表", "合并及公司资产负债表",
            "合併資產負債表", "Consolidated Balance Sheet",
        ],
        "income_statement": [
            "合并利润表", "合并及母公司利润表", "合并及公司利润表",
            "合併損益表", "合併綜合損益表", "Consolidated Income Statement",
        ],
        "cash_flow": [
            "合并现金流量表", "合并及母公司现金流量表", "合并及公司现金流量表",
            "合併現金流量表", "Consolidated Cash Flow Statement",
        ],
        "audit_opinion": [
            "审计报告", "審計報告", "Audit Report",
        ],
    }

    # --- 策略1：PDF书签（只匹配报表标题） ---
    if toc:
        for stmt_type, patterns in bookmark_keywords.items():
            for _, title, page in toc:
                title_clean = title.strip()
                for pat in patterns:
                    if pat in title_clean:
                        index[stmt_type] = page  # 1-indexed
                        break
                if stmt_type in index:
                    break

        # 如果书签中没有直接的报表标题，但有"财务报表"总入口
        if len(index) < 3:
            for _, title, page in toc:
                if "财务报表" in title.strip() and "附注" not in title.strip() and "编制" not in title.strip():
                    if "balance_sheet" not in index:
                        index["balance_sheet"] = page
                    break

    if len(index) >= 3:
        index["method"] = "bookmark"
        doc.close()
        return index

    # --- 策略2：LLM从目录页提取 ---
    toc_text = ""
    for i in range(min(30, doc.page_count)):
        text = doc[i].get_text()
        if "目录" in text[:100] or "目 录" in text[:100]:
            for j in range(i, min(i + 5, doc.page_count)):
                toc_text += doc[j].get_text() + "\n"
            break

    if toc_text and len(toc_text) > 100:
        try:
            client = get_client()
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=300,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"""请从以下年报目录文本中提取三张主要合并报表和审计报告的起始页码。

只返回JSON，格式如下：
{{"balance_sheet": 页码数字, "income_statement": 页码数字, "cash_flow": 页码数字, "audit_opinion": 页码数字}}

如果找不到某项，值设为null。只返回JSON，不要返回其他内容。

目录文本：
{toc_text[:3000]}"""
                }]
            )
            raw = response.choices[0].message.content.strip()
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                cleaned = cleaned.rsplit("```", 1)[0]
            llm_index = json.loads(cleaned.strip())

            for key in ["balance_sheet", "income_statement", "cash_flow", "audit_opinion"]:
                if key not in index and llm_index.get(key):
                    index[key] = int(llm_index[key])

            # 检查LLM结果质量：如果三张报表页码全相同，说明LLM只找到了章节入口
            stmt_pages = [index.get(k) for k in ["balance_sheet", "income_statement", "cash_flow"] if k in index]
            pages_distinct = len(set(stmt_pages)) >= 2
            if len(index) >= 3 and pages_distinct:
                index["method"] = "llm_toc"
                doc.close()
                return index
            # 页码相同 → 只是章节入口，保存hint后清空让策略3精确扫描
            if not pages_distinct and stmt_pages:
                index["_llm_hint"] = stmt_pages[0]  # 保存章节入口页作为扫描起点
                for k in ["balance_sheet", "income_statement", "cash_flow"]:
                    index.pop(k, None)
        except Exception:
            pass

    # --- 策略3：关键词扫描（ontology驱动） ---
    # 从LLM章节入口附近开始扫描（跳过目录、概况等前半部分）
    llm_hint = index.pop("_llm_hint", 0)
    if not llm_hint:
        llm_hint = min((v for v in index.values() if isinstance(v, int)), default=0)
    scan_start = max(0, llm_hint - 2) if llm_hint > 0 else 0  # 0-indexed

    for stmt_type, kws in all_keywords.items():
        if stmt_type in index and len(set(index.get(k) for k in ["balance_sheet", "income_statement", "cash_flow"] if k in index)) >= 2:
            continue  # 这个报表已有可靠定位
        for i in range(scan_start, doc.page_count):
            text = doc[i].get_text()
            for kw in kws:
                pos = text.find(kw)
                if pos < 0:
                    continue
                is_audit = "审计报告" in text[:100] or "审计意见" in text[:200]
                # 标题位置（前200字符）+ 有数字 + 不是审计报告页
                if pos < 200 and _is_data_page(text) and not is_audit:
                    index[stmt_type] = i + 1  # 1-indexed
                    break
                # 关键词在页面末尾 → 标题跨页
                if pos > len(text) * 0.7 and (i + 1) < doc.page_count:
                    index[stmt_type] = i + 2  # 下一页，1-indexed
                    break
            if stmt_type in index:
                break

    if index:
        index["method"] = "keyword_scan"

    doc.close()
    return index


CONTEXT_PAGES = {
    "balance_sheet": 4,
    "income_statement": 3,
    "cash_flow": 3,
    "audit_opinion": 4,
}


def find_financial_statements(pages: list[dict],
                              pdf_path: str | Path | None = None) -> dict[str, str]:
    """
    定位三张主要报表和审计意见的文本段落。
    统一通过 build_page_index 获取页码 → 直接按页码提取文本。
    """
    index = build_page_index(pdf_path) if pdf_path else {}
    result = {}

    for stmt_type, ctx in CONTEXT_PAGES.items():
        page_num = index.get(stmt_type)
        if isinstance(page_num, int) and page_num > 0:
            # 按页码直接提取：从起始页开始，取 context_pages 页
            idx = page_num - 1  # 0-indexed
            sections = []
            for offset in range(0, ctx + 1):
                i = idx + offset
                if 0 <= i < len(pages):
                    sections.append(f"=== 第{pages[i]['page']}页 ===\n{pages[i]['text']}")
            result[stmt_type] = "\n\n".join(sections)
        else:
            result[stmt_type] = ""

    result["_index_method"] = index.get("method", "none")
    return result


# ---------------------------------------------------------------------------
# 3. LLM提取结构化数据
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """你是专业的财务数据提取员。请从以下年报文本中提取合并报表的财务数据。

要求：
- 提取本期（当年）和上期（上年）两列数据
- 直接提取原文中的数字，不要做单位换算（系统会自动处理单位）
- 如果报表同时包含"合并"和"公司"两组列，只提取"合并"列的数据
- 括号内的数字表示负数，如 (299,584,935) 应提取为 -299584935
- "减：营业成本"等带"减："前缀的项目，提取其绝对值（正数），不带负号
- "财务费用"有的公司叫"财务收入"或"财务费用/(收入)"，如果是净收入则为负数
- "其中：利息费用"是财务费用的子项，注意提取正确层级
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

    # 页面已通过 build_page_index 精确定位，直接截取
    bs_text = sections["balance_sheet"][:8000]
    is_text = sections["income_statement"][:6000]
    cf_text = sections["cash_flow"][:5000]

    # 从ontology注入术语别名，提高跨公司/跨语言提取容错
    aliases_ref = _load_ontology_context()
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

    # Step 2: 定位报表页面（书签索引 → LLM目录 → 关键词）
    sections = find_financial_statements(pages, pdf_path=pdf_path)

    # 记录找到的页码和索引方法
    index_method = sections.pop("_index_method", "keyword")
    pages_found = {"_index_method": index_method}
    for key, text in sections.items():
        if isinstance(text, str):
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
    idx_method = result['pages_found'].get('_index_method', 'keyword')
    print(f"索引方法: {idx_method}")
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
