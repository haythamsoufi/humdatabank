"""
One-off script to build ai_tools/registry.py from ai_tools_registry.py.
- Keeps lines 1-46, adds imports from _utils and _query_utils, drops lines 47-326, keeps 327-end.
- Replaces helper names with package imports.
"""
import re

SRC = "app/services/ai_tools_registry.py"
DST = "app/services/ai_tools/registry.py"

def main():
    with open(SRC, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1-indexed: keep 1-46, insert new imports, then 327-end
    head = lines[:46]  # 0-45 inclusive
    tail = lines[326:]  # 326 to end (line 327 in 1-indexed)
    extra = [
        "\n",
        "from app.services.ai_tools._utils import (\n",
        "    log_tool_usage,\n",
        "    truncate_json_value,\n",
        "    ToolExecutionError,\n",
        ")\n",
        "from app.services.ai_tools._query_utils import (\n",
        "    infer_country_identifier_from_query,\n",
        "    rewrite_document_search_query,\n",
        ")\n",
        "from app.services.upr.query_detection import query_prefers_upr_documents\n",
        "\n",
    ]
    body = "".join(head) + "".join(extra) + "".join(tail)

    # Replace in-body references (registry uses these names)
    body = body.replace("_log_tool_usage(", "log_tool_usage(")
    body = body.replace("_truncate_json_value(", "truncate_json_value(")
    body = body.replace("_tool_cache_get(", "tool_cache_get(")
    body = body.replace("_tool_cache_set(", "tool_cache_set(")
    body = body.replace("_infer_country_identifier_from_query(", "infer_country_identifier_from_query(")
    body = body.replace("_query_prefers_upr_documents(", "query_prefers_upr_documents(")
    body = body.replace("_rewrite_document_search_query(", "rewrite_document_search_query(")
    body = body.replace('logger.debug("_rewrite_document_search_query failed:', 'logger.debug("rewrite_document_search_query failed:')

    with open(DST, "w", encoding="utf-8") as f:
        f.write(body)
    print("Wrote", DST)

if __name__ == "__main__":
    main()
