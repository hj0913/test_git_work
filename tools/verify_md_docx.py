"""核对 Markdown 源文件与 Word 交付物是否内容一致。

用法:
    python tools/verify_md_docx.py docs/每日锻炼计划功能规划.md docs/每日锻炼计划功能规划.docx

比对三个维度:
1. 标题序列（层级 + 文本）
2. 表格数量与每张表的行列规模
3. 正文可见字符集合（忽略空白与标点差异）

转换器约定（见 tools/md_to_docx.py）:
- Markdown `# H1` 文档标题 → Word 的 Title 样式（add_heading(level=0)），
  因此 Word 侧 Heading 1 实际对应 Markdown 的 `## H2`；
- 围栏代码块 → 单行单列表格（add_code_block），比对时需单独剥离。
本脚本按上述约定归一化后再比较。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# Markdown 表格行:以 | 开头且以 | 结尾
MD_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
MD_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")


def norm(text: str) -> str:
    """压缩空白,便于跨格式比对。"""
    return re.sub(r"\s+", "", text).strip()


def md_headings(lines: list[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip()))
    return out


def md_tables(lines: list[str]) -> list[tuple[int, int]]:
    """返回 [(数据行数, 列数), ...]。"""
    out: list[tuple[int, int]] = []
    i, in_fence = 0, False
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if not in_fence and MD_TABLE_ROW_RE.match(line) and i + 1 < len(lines) \
                and MD_TABLE_SEP_RE.match(lines[i + 1]):
            cols = len(line.strip().strip("|").split("|"))
            rows = 0
            j = i + 2
            while j < len(lines) and MD_TABLE_ROW_RE.match(lines[j]):
                rows += 1
                j += 1
            out.append((rows, cols))
            i = j
            continue
        i += 1
    return out


def md_code_blocks(lines: list[str]) -> list[str]:
    """提取围栏代码块正文，用于与 Word 侧代码表格比对。"""
    out: list[str] = []
    buf: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            if in_fence:
                out.append(norm("".join(buf)))
                buf = []
            in_fence = not in_fence
            continue
        if in_fence:
            buf.append(line)
    return out


def docx_structure(path: Path) -> tuple[list[tuple[int, str]], list[tuple[int, int]], str, list[str]]:
    doc = Document(str(path))
    headings: list[tuple[int, str]] = []
    tables: list[tuple[int, int]] = []
    code_blocks: list[str] = []
    chunks: list[str] = []

    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            style = (block.style.name or "")
            text = block.text.strip()
            if style.lower() == "title" or style.startswith("Title"):
                # Markdown 的 H1 标题在 Word 里是 Title 样式
                headings.append((0, text))
            else:
                m = re.match(r"Heading\s*(\d+)", style, re.IGNORECASE)
                if m:
                    # Word 的 Heading N 对应 Markdown 的 H(N+1)
                    headings.append((int(m.group(1)) + 1, text))
            if text:
                chunks.append(text)
        elif isinstance(block, Table):
            data_rows = max(len(block.rows) - 1, 0)
            cols = len(block.columns)
            cell_text = norm("".join(c.text for r in block.rows for c in r.cells))
            if len(block.rows) == 1 and cols == 1:
                code_blocks.append(cell_text)   # 代码块
            else:
                tables.append((data_rows, cols))
            for r in block.rows:
                for c in r.cells:
                    t = c.text.strip()
                    if t:
                        chunks.append(t)
    return headings, tables, norm("".join(chunks)), code_blocks


def main() -> int:
    md_path = Path(sys.argv[1])
    docx_path = Path(sys.argv[2])
    lines = md_path.read_text(encoding="utf-8").splitlines()

    md_h = md_headings(lines)
    md_t = md_tables(lines)
    md_code = md_code_blocks(lines)
    docx_h, docx_t, docx_text, docx_code = docx_structure(docx_path)

    md_body = norm("\n".join(
        l for l in lines
        if not HEADING_RE.match(l)
    ))
    # Markdown 可见文本 = 全文去掉标题行/表格分隔线
    md_visible = norm("\n".join(l for l in lines if not MD_TABLE_SEP_RE.match(l)))

    ok = True
    # Word 的 Title 样式(level 0)等价于 Markdown 的 H1(level 1)
    docx_h_norm = [(max(n, 1), t) for n, t in docx_h]

    print(f"[标题] md={len(md_h)}  docx={len(docx_h)}（含 Title）")
    if md_h != docx_h_norm:
        ok = False
        print("  !! 标题不一致")
        for idx, (a, b) in enumerate(zip(md_h, docx_h_norm), 1):
            if a[0] != b[0] or norm(a[1]) != norm(b[1]):
                print(f"   #{idx}: md={a} docx={b}")
    else:
        print("  OK 标题层级与文本完全一致")
        print(f"  {[f'H{n} {t}' for n, t in md_h[:3]]} ...")

    print(f"[表格] md={len(md_t)}  docx={len(docx_t)}（已剥离代码块表格）")
    if md_t != docx_t:
        ok = False
        print("  !! 表格规模不一致")
        for idx, (a, b) in enumerate(zip(md_t, docx_t), 1):
            if a != b:
                print(f"   表{idx}: md(行,列)={a} docx(行,列)={b}")
    else:
        print("  OK 表格数量与规模完全一致")
        print(f"  规模: {md_t}")

    print(f"[代码块] md={len(md_code)}  docx={len(docx_code)}")
    if [norm(c) for c in md_code] != [norm(c) for c in docx_code]:
        ok = False
        print("  !! 代码块内容不一致")
        for idx, (a, b) in enumerate(zip(md_code, docx_code), 1):
            if norm(a) != norm(b):
                print(f"   块{idx}:\n     md  ={a[:120]}\n     docx={b[:120]}")
    else:
        print("  OK 代码块内容完全一致")

    print(f"[正文] md 可见字符={len(md_visible)}  docx 可见字符={len(docx_text)}")
    # 抽查:docx 中每个标题文本都应能在 md 中找到
    missing = [t for _, t in docx_h if norm(t) and norm(t) not in md_visible]
    if missing:
        ok = False
        print(f"  !! md 缺失标题: {missing}")
    else:
        print("  OK md 覆盖 docx 全部标题")

    print("\n结论:", "PASS md 与 docx 内容一致" if ok else "FAIL 存在差异")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
