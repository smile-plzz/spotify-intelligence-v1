import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import alfred_intelligence as ai


def handler(request):
    path = request.path or "/"

    try:
        if path == "/api/intelligence":
            result = ai.compute_all_intelligence()
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps(result, default=str),
            }
        elif path == "/api/summary":
            result = ai.db_query_one(
                """
                SELECT
                    COUNT(*) as request_files,
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    SUM(cache_read_tokens) as total_cache_read,
                    SUM(cache_write_tokens) as total_cache_write,
                    SUM(reasoning_tokens) as total_reasoning,
                    SUM(api_call_count) as total_calls,
                    COUNT(DISTINCT session_id) as unique_sessions,
                    SUM(estimated_cost_usd) as total_cost
                FROM session_model_usage
                """
            ) or {}
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps(result, default=str),
            }
        elif path == "/api/health":
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"status": "ok", "db": ai.DB_PATH}),
            }
        else:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "not_found", "path": path}),
            }
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e), "traceback": traceback.format_exc()}),
        }
