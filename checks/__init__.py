"""检查器接口。

每个 checks/*.py 模块必须导出 `run(doc)`，返回一个 list[dict]。

一条结果长这样：

    {
      "id": "S-01",                    # 规则编号，与 SPEC 一致
      "level": "critical",             # critical / warn / hint
      "title": "缺少一级章节",          # 一句话，不超过 20 字
      "detail": "缺第 5 章『密码应用设计』",   # 具体到哪一处
      "location": "文档结构",           # 定位信息，"第 5 章" / "表 3" / "全文"
      "fix": "补写第 5 章，或在附录说明为何不涉及密码应用设计",
    }

约定：
- `detail` 可以说出章节名、表格序号、条款号，**但绝对不能出现原文句子片段**。
- `hint` 级别的结果不参与评分，reason 里要写清「为什么只提示不判错」。
- 检查项没命中就返回 `[]`，不要返回 None。

`doc` 是 core.SchemeDoc 的实例，提供：

    doc.paragraphs      list[dict]  {"text": str, "style": str, "index": int}
    doc.headings        list[dict]  {"text": str, "level": int, "index": int}
    doc.tables          list[list[list[str]]]   表格 → 行 → 单元格
    doc.full_text       str         全文（段落用 \\n 连接，不含表格）
    doc.filename        str         文件名（不含路径）
    doc.docx_bytes      int         原始文件字节数

不要 import docx、不要打开文件、不要读磁盘。所有数据都从 `doc` 拿。
"""

RULES = {}


def register(rule_id):
    """把 run() 挂到 RULES 上，供 audit.py 遍历。"""

    def deco(fn):
        RULES[rule_id] = fn
        return fn

    return deco
