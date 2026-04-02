import fitz  # pymupdf
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r"C:\Users\ADAM ZENG\Desktop\financial test\2023年立讯精密年报.pdf"
doc = fitz.open(pdf_path)

# Find the 合并资产负债表 page
balance_sheet_page = None
for i in range(len(doc)):
    text = doc[i].get_text()
    if "合并资产负债表" in text:
        balance_sheet_page = i
        break

print("=" * 80)
print("2023年立讯精密 - 合并资产负债表")
print("=" * 80)
print("\nFrom: 2023年立讯精密年报.pdf")
print(f"Balance Sheet starts on page {balance_sheet_page + 1}")
print("\n从合并资产负债表提取的数据:\n")

# Extract data from the consolidated balance sheet
# Page 117 contains the start with headers
# Pages 117-119 contain the main consolidated balance sheet

results = {}

for p in range(balance_sheet_page, min(balance_sheet_page + 8, len(doc))):
    text = doc[p].get_text()
    lines = text.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Find 应付票据
        if stripped == "应付票据" or (stripped.startswith("应付票据") and len(stripped) < 10):
            vals = []
            for j in range(i+1, min(i+3, len(lines))):
                nums = re.findall(r'[\d,.-]+', lines[j].strip())
                if nums:
                    vals.extend(nums)

            if len(vals) >= 2:
                key = f"应付票据_p{p+1}"
                results[key] = {"2023": vals[0], "2022": vals[1]}

        # Find 交易性金融负债
        if stripped == "交易性金融负债" or (stripped.startswith("交易性金融负债") and len(stripped) < 15):
            vals = []
            for j in range(i+1, min(i+3, len(lines))):
                nums = re.findall(r'[\d,.-]+', lines[j].strip())
                if nums:
                    vals.extend(nums)

            if len(vals) >= 2:
                key = f"交易性金融负债_p{p+1}"
                results[key] = {"2023": vals[0], "2022": vals[1]}

# Print results in a clean format
print("1. 应付票据 (Notes Payable):")
for key in sorted([k for k in results.keys() if "应付票据" in k]):
    page_num = key.split("_p")[1]
    data = results[key]
    print(f"   Page {page_num}:")
    print(f"      2023 (本期):  {data['2023']}")
    print(f"      2022 (上期):  {data['2022']}")

print("\n2. 交易性金融负债 (Trading Financial Liabilities):")
for key in sorted([k for k in results.keys() if "交易性金融负债" in k]):
    page_num = key.split("_p")[1]
    data = results[key]
    print(f"   Page {page_num}:")
    print(f"      2023 (本期):  {data['2023']}")
    print(f"      2022 (上期):  {data['2022']}")

print("\n" + "=" * 80)
print("\nNote: The main consolidated balance sheet (合并资产负债表) is on page 118.")
print("This is the primary financial statement for 立讯精密.")
print("=" * 80)

doc.close()
