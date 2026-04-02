import fitz  # pymupdf
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r"C:\Users\ADAM ZENG\Desktop\financial test\2023年立讯精密年报.pdf"
doc = fitz.open(pdf_path)

# First, find pages containing our target tables
targets = ["合并资产负债表", "合并利润表", "合并现金流量表"]
found_pages = {}

for i in range(len(doc)):
    text = doc[i].get_text()
    for t in targets:
        if t in text and t not in found_pages:
            found_pages[t] = i
            print(f"Found '{t}' on page {i+1}")

print(f"\nTotal pages: {len(doc)}")
print(f"Found tables: {found_pages}")

# Now extract text from relevant pages (and a few after each)
for table_name, page_idx in found_pages.items():
    print(f"\n{'='*80}")
    print(f"TABLE: {table_name} (pages {page_idx+1}-{page_idx+3})")
    print('='*80)
    for p in range(page_idx, min(page_idx + 4, len(doc))):
        text = doc[p].get_text()
        print(f"\n--- Page {p+1} ---")
        print(text[:8000])

doc.close()
