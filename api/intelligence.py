import json
import os
import sys

# Make parent directory importable so we can use alfred_intelligence
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import alfred_intelligence as ai

def handler(request):
    """Vercel serverless handler for /api/intelligence"""
    try:
        result = ai.compute_all_intelligence()
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(result, default=str),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e), "traceback": traceback.format_exc()}),
        }
