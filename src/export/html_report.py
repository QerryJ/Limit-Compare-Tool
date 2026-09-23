"""Offline HTML report export.

Constraint inherited from the project rules: the HTML must be a **single file
with inline CSS**, zero CDN, so it can be double-clicked or emailed without
any network access.
"""

import html
from typing import List, Tuple

from src.ui.theme import hex_color, verdict_color

_CSS_TEMPLATE = """
body{font-family:"Microsoft YaHei UI","Segoe UI",system-ui,sans-serif;font-size:13px;
line-height:1.6;color:%(text)s;background:%(bg)s;margin:0;padding:24px}
h1{font-size:18px;font-weight:500;margin:0 0 4px}
h2{font-size:14px;font-weight:500;margin:20px 0 8px;color:%(muted)s}
pre{background:%(surface)s;border-radius:8px;padding:12px;font-size:12px;
font-family:Consolas,monospace;white-space:pre-wrap;margin:0 0 16px}
table{border-collapse:collapse;width:100%%;font-size:12px}
th{background:%(surface)s;text-align:left;padding:6px 8px;border-bottom:1px solid %(border)s;
font-weight:500;white-space:nowrap}
td{padding:5px 8px;border-bottom:1px solid %(border)s;white-space:nowrap}
td.num{font-family:Consolas,monospace;text-align:right}
.verdict{font-weight:500}
.meta{color:%(muted)s;font-size:12px;margin-bottom:16px}
table.audit{width:auto;margin:0 0 20px;font-size:12px;border:1px solid %(border)s;
border-radius:8px;border-collapse:separate;overflow:hidden}
table.audit th{background:%(surface)s;text-align:left;padding:5px 10px;
font-weight:500;white-space:nowrap;color:%(muted)s;border-bottom:1px solid %(border)s}
table.audit td{padding:5px 10px;border-bottom:1px solid %(border)s;word-break:break-all}
table.audit tr:last-child th,table.audit tr:last-child td{border-bottom:none}
.filters{margin:0 0 10px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.filters label{font-size:12px;color:%(muted)s;display:inline-flex;gap:6px;align-items:center}
.filters select,.filters input{border:1px solid %(border)s;border-radius:6px;
padding:3px 8px;font-size:12px;font-family:inherit;background:%(bg)s;color:%(text)s}
#lc-count{font-size:12px;color:%(muted)s}
"""


# 表头筛选：内联 JS，零 CDN，仍是离线单文件（双击/邮件分发都能用）
_FILTER_JS = """
<script>
(function(){
  var sel=document.getElementById('lc-vfilter'),
      kw=document.getElementById('lc-kw'),
      cnt=document.getElementById('lc-count'),
      rows=[].slice.call(document.querySelectorAll('table.data tbody tr')),
      COL=%(col)d;
  function apply(){
    var v=sel?sel.value:'', q=((kw?kw.value:'')||'').toLowerCase(), n=0;
    rows.forEach(function(tr){
      var cell=tr.children[COL];
      var okv = !v || (cell && cell.textContent===v);
      var okq = !q || tr.textContent.toLowerCase().indexOf(q)>=0;
      var ok = okv && okq;
      tr.style.display = ok ? '' : 'none';
      if(ok) n++;
    });
    if(cnt) cnt.textContent='显示 '+n+' / '+rows.length+' 行';
  }
  if(sel) sel.addEventListener('change', apply);
  if(kw) kw.addEventListener('input', apply);
  apply();
})();
</script>
"""


def _build_filter(verdict_col: int, rows: List[List]) -> str:
    """判定列下拉 + 关键字输入框；默认全部，不预先隐藏任何行。"""
    selects = ""
    if verdict_col >= 0 and rows:
        values = sorted({str(r[verdict_col]) for r in rows if verdict_col < len(r)})
        options = "".join(
            f'<option value="{html.escape(v)}">{html.escape(v)}</option>'
            for v in values
        )
        selects = (
            '<label>判定 <select id="lc-vfilter">'
            '<option value="">全部</option>' + options + "</select></label>"
        )
    return (
        '<div class="filters">' + selects
        + '<label>关键字 <input id="lc-kw" type="search" '
          'placeholder="测试项 / Function"></label>'
        + '<span id="lc-count"></span></div>'
    )


def export_html_report(
    path: str,
    title: str,
    headers: List[str],
    rows: List[List],
    summary: str = "",
    verdict_col: int = -1,
    audit: List[Tuple[str, str]] = None,
) -> str:
    css = _CSS_TEMPLATE % {
        "text": hex_color("--lc-text"),
        "bg": hex_color("--lc-bg"),
        "muted": hex_color("--lc-text-muted"),
        "surface": hex_color("--lc-surface"),
        "border": "#e3e3df",
    }

    if verdict_col < 0:
        for idx, head in enumerate(headers):
            if head in ("判定", "方向", "状态"):
                verdict_col = idx
                break

    head_html = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body_html = []
    for row in rows:
        cells = []
        for col, value in enumerate(row):
            text = html.escape(str(value))
            if col == verdict_col:
                # Colour is never the only signal: the text is always rendered.
                cells.append(
                    f'<td class="verdict" style="color:{verdict_color(str(value))}">'
                    f"{text}</td>"
                )
            else:
                cells.append(f"<td>{text}</td>")
        body_html.append("<tr>" + "".join(cells) + "</tr>")

    summary_html = (
        f"<h2>对比总结</h2><pre>{html.escape(summary)}</pre>" if summary else ""
    )
    audit_html = ""
    if audit:
        audit_rows = "".join(
            f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
            for k, v in audit
        )
        audit_html = (
            "<h2>稽核信息</h2><table class=\"audit\">" + audit_rows + "</table>"
        )
    document = (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{css}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f'<div class="meta">共 {len(rows)} 行 · 离线单文件报告（含表头筛选）</div>'
        f"{audit_html}"
        f"{summary_html}"
        f"{_build_filter(verdict_col, rows)}"
        f"<table class=\"data\"><thead><tr>{head_html}</tr></thead><tbody>"
        + "".join(body_html)
        + "</tbody></table>"
        + (_FILTER_JS % {"col": max(verdict_col, 0)} if rows else "")
        + "</body></html>"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(document)
    return path
